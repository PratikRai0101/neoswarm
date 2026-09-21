"""Provider-agnostic browser sub-agent runner.

Browser workers reuse NeoSwarm's provider adapters while driving browser
interactions directly through ``ws_manager``. Sub-agents appear as visible
AgentSession cards on the dashboard.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from uuid import uuid4

from backend.apps.agents.models import AgentSession, ApprovalRequest, Message
from backend.apps.agents.ws_manager import ws_manager
from backend.apps.tools_lib.tools_lib import load_builtin_permissions

logger = logging.getLogger(__name__)

# Cache provider-formatted conversation history per browser and model provider
# so successive BrowserAgent calls can resume without mixing wire formats.
_browser_history: dict[tuple[str, str], list] = {}
# Cap history to prevent unbounded growth on long-lived browsers.
_MAX_HISTORY_MESSAGES = 30


def clear_browser_history(browser_id: str) -> None:
    """Drop cached conversation history for a browser (e.g. when it's closed)."""
    for key in [key for key in _browser_history if key[0] == browser_id]:
        _browser_history.pop(key, None)


def _trim_provider_history(messages: list, max_messages: int) -> list:
    """Bound generic history without cutting into a provider tool-use turn."""
    if len(messages) <= max_messages:
        return list(messages)
    start = len(messages) - max_messages
    while start > 0 and getattr(messages[start], "role", "") != "user":
        start -= 1
    return list(messages[start:])


# ---------------------------------------------------------------------------
# Loop detection
#
# Tracks recent state-mutating tool calls in a sliding window. If the model
# repeats the same (tool, input) with the same result several times, we
# inject an is_error message in the next tool_result to force a strategy
# change. This prevents the model from burning the entire turn budget on
# a failing approach.
# ---------------------------------------------------------------------------

# Tools that are read-only / idempotent and should NOT count toward loop
# detection. Repeating these is normal (scrolling through a feed, taking
# successive screenshots, polling for an element to appear).
_LOOP_DETECTION_EXCLUDED_TOOLS = {
    "BrowserScreenshot",
    "BrowserGetText",
    "BrowserGetElements",
    "BrowserListInteractives",  # Phase 3
    "BrowserWait",
    "ReportProgress",  # Phase 2
    "RequestHumanIntervention",
    "RequestUserText",
}

_LOOP_WINDOW_SIZE = 5
_LOOP_REPEAT_THRESHOLD = 3
_LOOP_HARD_CAP = 5


def _hash_tool_call(tool_name: str, tool_input: dict, result: dict) -> tuple[str, str, str]:
    """Build a stable hash key for a tool call, including its result.

    Including the result hash means that legitimate progress (same input,
    different output — e.g. BrowserScroll on a long feed) does NOT count
    as a loop. Only same-input + same-output is treated as stuck.
    """
    try:
        input_key = json.dumps(tool_input, sort_keys=True, default=str)
    except Exception:
        input_key = repr(tool_input)
    try:
        # Truncate the result hash to avoid huge image blobs in the key
        result_key = json.dumps(result, sort_keys=True, default=str)[:300]
    except Exception:
        result_key = repr(result)[:300]
    return (tool_name, input_key, result_key)


def _detect_loop(
    recent_calls: list[tuple[str, str, str]],
    new_call: tuple[str, str, str],
) -> bool:
    """Return True if `new_call` constitutes a loop given recent history.

    A loop is when the same (tool, input, result) has appeared at least
    `_LOOP_REPEAT_THRESHOLD` times within the last `_LOOP_WINDOW_SIZE`
    state-mutating calls (the new call counts as one of those occurrences).
    """
    if new_call[0] in _LOOP_DETECTION_EXCLUDED_TOOLS:
        return False
    window = recent_calls[-(_LOOP_WINDOW_SIZE - 1):] + [new_call]
    matches = sum(1 for c in window if c == new_call)
    return matches >= _LOOP_REPEAT_THRESHOLD


_LOOP_WARNING_TEXT = (
    "LOOP DETECTED: You have called this tool with these exact parameters and "
    "gotten the same result {count} times in a row. STOP retrying this approach "
    "— it is not working. Try a fundamentally different strategy: "
    "(1) check the page state with BrowserScreenshot or BrowserGetText, "
    "(2) try a different selector or a different tool, "
    "(3) use BrowserPressKey for keyboard shortcuts if the site supports them, "
    "or (4) call RequestHumanIntervention if you genuinely cannot proceed."
)


# ---------------------------------------------------------------------------
# Dead-card and stagnation guards (ported from upstream browser_loop)
#
# A card the agent cannot make progress on — either gone (closed, or the
# dashboard is not mounted) or hung (every command times out) — looks identical
# to a transient failure from inside the loop. Retrying just burns the whole
# turn budget, so a sustained pattern fails fast instead. The streak resets on
# any good result, so a merely-busy page that recovers is never mistaken for
# dead.
# ---------------------------------------------------------------------------

_CARD_GONE_MARKERS = (
    "not an electron webview",    # card closed / destroyed
    "no dashboard is connected",  # dashboard view not mounted
    "command timed out",          # hung: the command never came back
    "page unresponsive",          # hung: the page never responded
    "browser webview",            # Tauri: "Browser webview '<label>' was not found"
    "was not found",              # card missing in either host
)
CARD_GONE_LIMIT = 2  # consecutive misses before giving up (absorbs one transient)


def card_is_unavailable(result: dict) -> bool:
    """True when the browser card is gone or wedged, so retrying cannot help."""
    err = str(result.get("error") or "").lower()
    return any(marker in err for marker in _CARD_GONE_MARKERS)


_FAILURE_MARKERS = (
    "error", "not found", "no longer valid", "no box model",
    "no valid bounding rect", "failed", "rejected", "timed out",
    "could not", "unable to", "denied",
)


def looks_like_failure(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in _FAILURE_MARKERS)


# Read-only / meta tools never count toward stagnation: re-orienting is not
# being stuck.
STAGNATION_ESCALATION_AT = 3
STAGNATION_MAX = 5


def is_unproductive(
    tool_name: str, result: dict, prev_url: str, prev_text: str,
) -> bool:
    """True if a state-mutating action changed nothing observable.

    A URL change or a success-shaped result gets the benefit of the doubt (a
    click that opens a dropdown changes no URL but is real progress). An error,
    a failure-shaped message, or the exact same observation as the previous
    action — all with no URL change — counts as unproductive.
    """
    if tool_name in _LOOP_DETECTION_EXCLUDED_TOOLS:
        return False
    new_url = str(result.get("url") or "")
    if new_url and prev_url and new_url != prev_url:
        return False
    if "error" in result:
        return True
    text = str(result.get("text") or result.get("error") or "")
    if looks_like_failure(text):
        return True
    if prev_text and text[:200] == prev_text[:200]:
        return True
    return False


_STAGNATION_NUDGE = (
    "NO PROGRESS: your last {streak} actions changed nothing and looked like "
    "failures. Before trying yet another variation, find out WHY: read the exact "
    "errors; use BrowserEvaluate to check whether the target is disabled, hidden, "
    "or behind an overlay; take ONE BrowserGetText or BrowserScreenshot to confirm "
    "the page is what you think (not a login wall, captcha, or error page). Act on "
    "the real cause; only if it is truly a selector miss do you walk the ladder "
    "(BrowserListInteractives + BrowserClickIndex, then BrowserPressKey, then "
    "find-by-text with BrowserEvaluate)."
)


def stagnation_nudge(streak: int) -> str:
    base = _STAGNATION_NUDGE.format(streak=streak)
    if streak >= STAGNATION_MAX:
        base += (
            " Switching selectors hasn't worked, so the PLAN itself is likely "
            "wrong: step back and revise your overall approach (a different page, "
            "route, or entry point), not just the selector. If you still cannot "
            "make progress, call RequestHumanIntervention."
        )
    return base


def advance_stagnation(
    streak: int, prev_url: str, prev_text: str, tool_name: str, result: dict,
) -> tuple[int, str, str, str | None]:
    """Advance the stagnation streak for one executed tool.

    Neutral read/meta tools pass through unchanged. For a state-mutating action
    the streak bumps when unproductive and resets otherwise. Returns
    (new_streak, new_prev_url, new_prev_text, nudge_or_None).
    """
    if tool_name in _LOOP_DETECTION_EXCLUDED_TOOLS:
        return streak, prev_url, prev_text, None
    if is_unproductive(tool_name, result, prev_url, prev_text):
        streak += 1
    else:
        streak = 0
    new_url = str(result.get("url") or "") or prev_url
    new_text = str(result.get("text") or result.get("error") or "")[:200]
    nudge = (
        stagnation_nudge(streak)
        if streak in (STAGNATION_ESCALATION_AT, STAGNATION_MAX)
        else None
    )
    return streak, new_url, new_text, nudge


def stagnation_exhausted(streak: int) -> bool:
    """True once deterministic nudging has been exhausted."""
    return streak >= STAGNATION_MAX


# ---------------------------------------------------------------------------
# Completion honesty gate
#
# A model that ends its turn is not proof the goal happened. This gate
# reality-checks the run before the status is allowed to say "done", so a fake
# success is reported as the failure it is. It is deliberately conservative: it
# flags only unambiguous ghosts.
# ---------------------------------------------------------------------------

# State-changing tools: a task that needed to DO something must land one.
_PRODUCTIVE_TOOLS = {
    "BrowserClick", "BrowserClickIndex", "BrowserType", "BrowserNavigate",
    "BrowserPressKey", "BrowserScroll", "BrowserBatch", "BrowserHover",
}
# Read/extract tools: a look-only task's evidence is that a read returned content.
_READ_TOOLS = {
    "BrowserGetText", "BrowserGetElements", "BrowserListInteractives",
    "BrowserScreenshot", "BrowserEvaluate",
}


def completion_is_honest(action_log: list[dict]) -> tuple[bool, str]:
    """Reality-check a run the model declared done. Returns (honest, reason).

    Flags only the unambiguous ghosts: a run that took no action at all, one
    whose every state-changing action errored, or one that only looked around
    without any read returning content. A partially erroring run that still
    landed a real action stays honest.
    """
    if not action_log:
        return False, "declared done without taking a single action"
    actions = [a for a in action_log if a.get("tool") in _PRODUCTIVE_TOOLS]
    actions_ok = [a for a in actions if a.get("ok")]
    reads_ok = [
        a for a in action_log
        if a.get("tool") in _READ_TOOLS and a.get("ok")
        and str(a.get("result_summary") or "").strip()
    ]
    if actions and not actions_ok:
        return False, "every state-changing action failed"
    if not actions and not reads_ok:
        return False, "only looked around: no action taken and no content read back"
    return True, ""


BROWSER_TOOLS_SCHEMA = [
    {
        "name": "ReportProgress",
        "description": (
            "Record your assessment of the previous action and your plan for the "
            "next one. You MUST call this BEFORE any browser action tools in every "
            "turn (after the very first turn). This is how you reflect on what just "
            "happened, track what you've learned about this site, and articulate what "
            "you're trying to do next. Skipping it is not allowed and will be rejected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "evaluation_previous": {
                    "type": "string",
                    "description": (
                        "What did the previous action(s) accomplish? Did they succeed? "
                        "If not, why? Be specific about what changed on the page."
                    ),
                },
                "working_memory": {
                    "type": "string",
                    "description": (
                        "Short notes about what you've learned about this site so far — "
                        "selectors that work, keyboard shortcuts, layout quirks, what "
                        "you've tried that failed. Carry this forward across turns."
                    ),
                },
                "next_goal": {
                    "type": "string",
                    "description": (
                        "What you're trying to achieve with the action(s) you're about "
                        "to take next. Be concrete."
                    ),
                },
            },
            "required": ["evaluation_previous", "working_memory", "next_goal"],
        },
    },
    {
        "name": "BrowserScreenshot",
        "description": (
            "Capture a screenshot of the browser page. Returns the screenshot as a "
            "base64-encoded PNG image. Use this to see what is currently displayed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "BrowserGetText",
        "description": (
            "Get the visible text content of the browser page. Returns up to 15000 characters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "BrowserNavigate",
        "description": "Navigate the browser to a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "BrowserClick",
        "description": "Click an element identified by a CSS selector. Use BrowserGetElements first to discover valid selectors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the element to click."},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "BrowserType",
        "description": "Type text into an input element. Clears existing value first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the input element."},
                "text": {"type": "string", "description": "The text to type."},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "BrowserEvaluate",
        "description": "Evaluate a JavaScript expression in the browser page and return the result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "JavaScript expression to evaluate."},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "BrowserGetElements",
        "description": (
            "Get a list of interactive elements on the page with CSS selectors. "
            "Call this BEFORE clicking or typing so you know which selectors are valid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to scope the search (e.g. 'form', '#main'). Defaults to 'body'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "BrowserScroll",
        "description": (
            "Scroll the page up or down. Automatically finds the correct scrollable "
            "container (works on SPAs like Notion, Gmail, etc. that use nested scroll "
            "containers instead of window-level scrolling). Returns scroll position info "
            "including whether top/bottom has been reached."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction. Defaults to 'down'.",
                },
                "amount": {
                    "type": "number",
                    "description": "Pixels to scroll. Defaults to 500.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "BrowserListInteractives",
        "description": (
            "Get a NUMBERED LIST of interactive elements on the page using the "
            "browser's accessibility tree. Returns elements like [1]<button \"Like\">, "
            "[2]<link \"Settings\">, etc. Use this BEFORE BrowserClickIndex. This is "
            "the PREFERRED way to discover clickable elements on hostile sites "
            "(Tinder, Instagram, TikTok) where CSS selectors fail because the page "
            "uses unlabeled <div>s — the accessibility tree sees roles and names "
            "even when raw HTML doesn't expose them. Much more reliable than "
            "BrowserGetElements (which uses CSS selectors)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "BrowserClickIndex",
        "description": (
            "Click an element by its numeric index from BrowserListInteractives. "
            "Uses native OS-level mouse events (event.isTrusted=true) so it works "
            "on sites that filter out synthetic JS events. Always call "
            "BrowserListInteractives first to get a fresh index list. If the click "
            "returns 'index no longer valid', the page changed — re-list and retry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "The numeric index from BrowserListInteractives (1-based).",
                },
            },
            "required": ["index"],
        },
    },
    {
        "name": "BrowserHover",
        "description": (
            "Hover the pointer over an element identified by a CSS selector. "
            "Use this to open :hover menus, dropdowns, and tooltips before "
            "reading or clicking their contents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the element to hover.",
                },
            },
            "required": ["selector"],
        },
    },
    {
        "name": "BrowserBatch",
        "description": (
            "Run a sequence of browser actions in one tool call. Each sub-action "
            "is executed in order, with the URL captured before/after each one. "
            "If the URL changes mid-batch (the page navigated), the rest of the "
            "batch is aborted and you get a partial result. Use this when you "
            "have a known sequence — typing then pressing Enter, swiping multiple "
            "times, clicking through pagination. Max 5 actions per batch.\n\n"
            "Sub-action types and their params:\n"
            "- click_index: { index: int }\n"
            "- press_key: { key: str }\n"
            "- type: { selector: str, text: str }\n"
            "- click: { selector: str }\n"
            "- scroll: { direction?: 'up'|'down', amount?: int }\n"
            "- wait: { milliseconds?: int }\n"
            "- navigate: { url: str }\n"
            "- hover: { selector: str }\n\n"
            "Example: { actions: [{type: 'click_index', params: {index: 1}}, "
            "{type: 'wait', params: {milliseconds: 500}}, "
            "{type: 'press_key', params: {key: 'ArrowRight'}}] }"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["click_index", "press_key", "type", "wait", "scroll", "navigate", "click", "hover"],
                            },
                            "params": {"type": "object"},
                        },
                        "required": ["type", "params"],
                    },
                },
            },
            "required": ["actions"],
        },
    },
    {
        "name": "BrowserPressKey",
        "description": (
            "Press a keyboard key (or key combination) on the page using a real native "
            "input event. Use this for keyboard shortcuts when JS-dispatched events get "
            "ignored — sites like Tinder, Slack, Notion, Gmail listen for trusted key "
            "events. Examples: 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape', 'Tab', "
            "'Space', single letters like 'a'. Prefer this over BrowserEvaluate with "
            "dispatchEvent for keyboard shortcuts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "The key to press. Use JS KeyboardEvent.key names like "
                        "'ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Tab', 'Space', "
                        "'Backspace', or a single character like 'a'."
                    ),
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "BrowserWait",
        "description": (
            "Wait for a specified duration. Useful after navigation or actions that "
            "trigger page loads, animations, or async content rendering. "
            "Min 100ms, max 10000ms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "milliseconds": {
                    "type": "number",
                    "description": "Duration to wait in milliseconds. Defaults to 1000.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "RequestHumanIntervention",
        "description": (
            "Request the user's help when you encounter an obstacle you cannot solve "
            "programmatically — captchas, login prompts, cookie consent walls, "
            "two-factor authentication, or any blocking popup. The agent will pause "
            "until the user resolves the issue and clicks Continue."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "problem": {
                    "type": "string",
                    "description": (
                        "One short sentence describing the obstacle. Keep it under "
                        "15 words. Example: 'Login required — please sign in to X/Twitter.'"
                    ),
                },
                "instruction": {
                    "type": "string",
                    "description": (
                        "One short sentence telling the user what to do. Keep it under "
                        "15 words. Example: 'Log in with your credentials, then click Done.'"
                    ),
                },
            },
            "required": ["problem", "instruction"],
        },
    },
    {
        "name": "RequestUserText",
        "description": (
            "Ask the user a short question and wait for their typed answer — "
            "for choices, credentials you must not guess, or confirmations that "
            "need an explicit reply. The user's answer (or cancellation) is "
            "returned as this tool's result. Prefer RequestHumanIntervention "
            "when the user must DO something in the browser instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "One short question for the user.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional one-line background shown with the question.",
                },
            },
            "required": ["question"],
        },
    },
]

ACTION_MAP = {
    "BrowserScreenshot": "screenshot",
    "BrowserGetText": "get_text",
    "BrowserNavigate": "navigate",
    "BrowserClick": "click",
    "BrowserType": "type",
    "BrowserEvaluate": "evaluate",
    "BrowserGetElements": "get_elements",
    "BrowserScroll": "scroll",
    "BrowserWait": "wait",
    "BrowserPressKey": "press_key",
    "BrowserListInteractives": "list_interactives",
    "BrowserClickIndex": "click_index",
    "BrowserHover": "hover",
    "BrowserBatch": "batch",
}

SYSTEM_PROMPT = (
    "You are a website-agnostic browser automation agent. You can operate on ANY "
    "website the user is signed into — social media, dating apps, email, productivity "
    "tools, dashboards, ecommerce, anything. Assume the user has already logged in.\n\n"

    "## Required output structure: ReportProgress before every action\n"
    "Before ANY action tool (BrowserClick, BrowserType, BrowserNavigate, "
    "BrowserPressKey, BrowserScroll, BrowserEvaluate, BrowserClickIndex, "
    "BrowserBatch), you MUST call the ReportProgress tool in the SAME turn. "
    "ReportProgress takes three short fields:\n"
    "- evaluation_previous: did your last action work? what changed on the page?\n"
    "- working_memory: what have you learned about this site? what worked, what didn't?\n"
    "- next_goal: what specifically are you trying to do with the next action?\n"
    "Emit ReportProgress and your action tool(s) together in the same response. "
    "If you skip ReportProgress, your action tools will be REJECTED with an error "
    "and you will have to retry. This is not optional. Read-only tools "
    "(BrowserScreenshot, BrowserGetText, BrowserGetElements, BrowserWait) do not "
    "require ReportProgress.\n\n"

    "## Loop awareness\n"
    "If you see a tool result containing 'LOOP DETECTED' or '⚠️', it means you "
    "have called the same tool with the same parameters and gotten the same "
    "result multiple times in a row. STOP. Do NOT retry the same approach. "
    "Switch strategy entirely: try a different tool, a different selector, "
    "keyboard shortcuts, or call RequestHumanIntervention if you genuinely "
    "cannot proceed. The loop detector will force-exit the agent if you "
    "ignore it more than 5 times.\n\n"

    "## Use prior context\n"
    "If this is a continuation of an earlier conversation on the same browser, the "
    "messages above already contain everything you've tried, what worked, what failed, "
    "and the page state. READ THAT HISTORY before acting. Do NOT take a fresh screenshot "
    "or re-explore the DOM if you already know what's on screen — just act. Only re-orient "
    "if the page has clearly changed (after navigation, after a multi-second wait, or if "
    "your last action mutated the page in unexpected ways).\n\n"

    "## Try multiple strategies, learn from failures\n"
    "Sites vary wildly. When one approach fails, switch tactics — don't retry the same "
    "thing. The escalation ladder, fastest to slowest:\n"
    "1. **Keyboard shortcuts via BrowserPressKey** — fastest and most reliable on sites "
    "that support them (Tinder swipes, Gmail navigation, Slack message jump, etc.). "
    "Always check if the site shows keyboard hints in the UI before falling back to clicks. "
    "BrowserPressKey sends real native events that pass the `event.isTrusted` check, so "
    "it works where dispatchEvent in BrowserEvaluate silently fails.\n"
    "2. **Accessibility tree via BrowserListInteractives + BrowserClickIndex** — the "
    "accessibility tree sees roles and names that the raw DOM doesn't, even on sites "
    "like Tinder, Instagram, and TikTok that use unlabeled <div>s with click handlers. "
    "Call BrowserListInteractives to get a numbered list (`[1]<button \"Like\">`, "
    "`[2]<link \"Settings\">`), then BrowserClickIndex with the number. The click uses "
    "native OS-level mouse events so it works where DOM .click() doesn't. THIS IS YOUR "
    "GO-TO STRATEGY for unlabeled or hostile sites — try this BEFORE BrowserGetElements.\n"
    "3. **Semantic CSS selectors** — `button[aria-label='X']`, `[role='button']`, "
    "`a[href*='...']`. Try these via BrowserGetElements + BrowserClick when the site "
    "actually has semantic HTML.\n"
    "4. **Text-based JS query** — when both of the above fail, use BrowserEvaluate to "
    "find elements by visible text: `Array.from(document.querySelectorAll('*')).find(el => el.textContent.trim() === 'Like')`.\n"
    "5. **Coordinate-based fallback** — last resort: take a screenshot, identify the "
    "button visually, then click by approximate coords.\n\n"

    "## Batch known sequences with BrowserBatch\n"
    "When you have a known sequence of actions — typing then pressing Enter, "
    "swiping multiple times, clicking through pagination — emit them all in a "
    "single BrowserBatch call instead of one tool per turn. The batch executes "
    "sub-actions sequentially and aborts if the URL changes mid-batch (so you "
    "won't operate on stale state). Max 5 sub-actions per batch.\n"
    "Use BrowserBatch when:\n"
    "- You're doing the same action repeatedly (5 swipes, 3 scrolls)\n"
    "- You have a deterministic flow (type query → press Enter → click first result)\n"
    "Don't use BrowserBatch when:\n"
    "- You need to read the page state between actions\n"
    "- You're uncertain about what comes next\n"
    "- An action might trigger an unexpected popup or navigation\n\n"

    "## Avoid wasted cycles\n"
    "- Do NOT screenshot after every single action. Screenshot ONLY when you genuinely "
    "don't know the page state (start of task, after navigation, after a failure).\n"
    "- Do NOT call BrowserGetElements on the entire body if you already know roughly "
    "where the target is. Scope it: `BrowserGetElements({selector: 'nav'})`.\n"
    "- Do NOT call the same failing tool twice with identical parameters. If selector "
    "X failed, try a DIFFERENT selector or a DIFFERENT strategy.\n"
    "- For repeated actions (swiping through profiles, going through inbox messages), "
    "use BrowserPressKey if available — it's an order of magnitude faster than DOM clicks.\n\n"

    "## When you genuinely cannot proceed\n"
    "Use RequestHumanIntervention for:\n"
    "- Login walls (the user thinks they're logged in but the session expired)\n"
    "- Captchas, 2FA prompts, age verification gates\n"
    "- Anything genuinely ambiguous about user intent\n"
    "Don't use it for normal tool failures — try a different approach first.\n"
    "Use RequestUserText when you need a typed answer (a choice, a confirmation,\n"
    "or information only the user knows) rather than an action in the browser.\n"
    "If a tool result says the browser is under user control, stop acting on it:\n"
    "tell the user what you were doing and ask them to return the browser.\n\n"

    "## Tool reference\n"
    "- BrowserScreenshot: visual snapshot. Use sparingly, not after every action.\n"
    "- BrowserGetText: returns up to 15000 chars of visible text. Useful for reading "
    "content without an image.\n"
    "- BrowserScroll: handles nested scroll containers (Notion, Gmail). Returns "
    "atTop/atBottom — stop looping when scroll delta is 0.\n"
    "- BrowserGetElements: enumerate interactive elements with selectors.\n"
"- BrowserClick / BrowserType: standard DOM interaction.\n"
"- BrowserHover: open :hover menus, dropdowns, and tooltips before interacting.\n"
"- BrowserPressKey: native key events (preferred for shortcuts).\n"
    "- BrowserEvaluate: arbitrary JS for everything else, including text-based element "
    "search and reading state. Avoid for scrolling and keyboard events.\n"
    "- BrowserWait: 1-3s after navigation, 0.5s after most clicks.\n"
"- Popups open as their own card tabs (their opener is remembered); closing a\n"
"popup tab returns to the page that spawned it.\n\n"

    "Complete the task autonomously and report a clear, brief summary."
)

MAX_TURNS = 40

# Largest text observation handed to the model. Larger pages are truncated
# with an honest note (see _format_tool_result).
_MAX_TOOL_TEXT_CHARS = 30_000

# Tools that count as "action tools" — calling any of these in a turn requires
# the model to also call ReportProgress in the same turn (after the first
# turn). Read-only tools and meta tools are exempt.
_ACTION_TOOLS_REQUIRING_REPORT = {
    "BrowserClick",
    "BrowserType",
    "BrowserNavigate",
    "BrowserPressKey",
    "BrowserScroll",
    "BrowserEvaluate",
    "BrowserClickIndex",  # Phase 3
    "BrowserBatch",  # Phase 4
}


async def execute_browser_tool(
    tool_name: str, tool_input: dict, browser_id: str, tab_id: str = "",
) -> dict:
    """Execute a browser tool via ws_manager directly (no MCP/HTTP round-trip)."""
    action = ACTION_MAP.get(tool_name)
    if not action:
        return {"error": f"Unknown browser tool: {tool_name}"}

    params = {k: v for k, v in tool_input.items()}
    request_id = uuid4().hex
    result = await ws_manager.send_browser_command(
        request_id, action, browser_id, params, tab_id=tab_id,
    )
    return result


def _format_tool_result(result: dict, tool_name: str) -> list[dict]:
    """Convert a browser command result into provider-agnostic content blocks.

    Text observations are bounded so one huge page cannot flood the model's
    context; the bound is reported honestly in the result itself.
    """
    if "error" in result:
        return [{"type": "text", "text": f"Error: {result['error']}"}]

    if tool_name == "BrowserScreenshot" and result.get("image"):
        blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": result["image"],
                },
            },
            {"type": "text", "text": f"Screenshot captured. URL: {result.get('url', 'unknown')}"},
        ]
        return blocks

    text = str(result.get("text", json.dumps(result)))
    if len(text) > _MAX_TOOL_TEXT_CHARS:
        text = (
            text[:_MAX_TOOL_TEXT_CHARS]
            + f"\n... (observation truncated at {_MAX_TOOL_TEXT_CHARS} chars; "
            "use a scoped selector or BrowserGetText to read the rest)"
        )
    return [{"type": "text", "text": text}]


async def _request_browser_approval(
    session: AgentSession, tool_name: str, tool_input: dict,
) -> dict:
    """Send an approval request for a browser sub-agent tool and wait for the decision."""
    request_id = uuid4().hex
    approval_req = ApprovalRequest(
        id=request_id,
        session_id=session.id,
        tool_name=tool_name,
        tool_input=tool_input,
    )
    session.pending_approvals.append(approval_req)
    session.status = "waiting_approval"

    await ws_manager.send_to_session(session.id, "agent:status", {
        "session_id": session.id,
        "status": "waiting_approval",
    })

    try:
        decision = await asyncio.wait_for(
            ws_manager.send_approval_request(
                session.id, request_id, tool_name, tool_input,
            ),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        decision = {"behavior": "deny", "message": "Approval timed out"}

    session.pending_approvals = [
        a for a in session.pending_approvals if a.id != request_id
    ]
    session.status = "running"
    await ws_manager.send_to_session(session.id, "agent:status", {
        "session_id": session.id,
        "status": "running",
    })
    return decision


async def run_browser_agent(
    task: str,
    browser_id: str,
    model: str,
    dashboard_id: str | None = None,
    tab_id: str = "",
    pre_selected: bool = False,
    initial_url: str | None = None,
    parent_session_id: str | None = None,
) -> dict:
    """Run a browser sub-agent loop for a single browser card.

    Creates a visible AgentSession, streams progress via WebSocket,
    and returns the full action log + summary + final screenshot.
    """
    if not browser_id and not dashboard_id:
        # A dashboard-less session asking for a browser: say so in one line
        # instead of starting a loop whose every tool call hangs and times out.
        return {
            "session_id": "",
            "browser_id": "",
            "summary": (
                "Error: this session has no browser card. "
                "Create one from a dashboard before delegating browser tasks."
            ),
            "action_log": [],
            "final_screenshot": None,
        }

    from backend.apps.agents.agent_manager import agent_manager

    _browser_perms = load_builtin_permissions()

    session_id = uuid4().hex
    cancel_event = asyncio.Event()
    session = AgentSession(
        id=session_id,
        name=f"Browser Agent",
        model=model,
        mode="browser-agent",
        status="running",
        dashboard_id=dashboard_id,
        browser_id=browser_id,
        system_prompt=SYSTEM_PROMPT,
        parent_session_id=parent_session_id,
    )
    session._cancel_event = cancel_event
    agent_manager.sessions[session_id] = session

    # If parent was already stopped before we registered, bail immediately
    if parent_session_id:
        parent = agent_manager.sessions.get(parent_session_id)
        if parent and parent.status == "stopped":
            cancel_event.set()

    await ws_manager.send_to_session(session_id, "agent:status", {
        "session_id": session_id,
        "status": "running",
        "session": session.model_dump(mode="json"),
    })

    if initial_url:
        nav_result = await execute_browser_tool(
            "BrowserNavigate", {"url": initial_url}, browser_id, tab_id,
        )
        logger.info(f"Browser agent {session_id}: navigated to {initial_url}: {nav_result.get('text', nav_result.get('error', ''))}")

    from backend.apps.settings.settings import load_settings
    from backend.apps.agents.providers.base import ProviderMessage, ToolSchema
    from backend.apps.agents.providers.registry import create_provider, provider_for_model

    browser_settings = load_settings()
    parent = agent_manager.sessions.get(parent_session_id) if parent_session_id else None
    fallback_provider = parent.provider if parent else "anthropic"
    provider_name = provider_for_model(model, fallback=fallback_provider)
    session.provider = provider_name
    try:
        provider = create_provider(provider_name, browser_settings)
    except ValueError as exc:
        session.status = "error"
        error_text = f"Browser agent cannot use {provider_name}/{model}: {exc}"
        err_msg = Message(role="system", content=f"Error: {error_text}")
        session.messages.append(err_msg)
        await ws_manager.send_to_session(session_id, "agent:message", {
            "session_id": session_id,
            "message": err_msg.model_dump(mode="json"),
        })
        await ws_manager.send_to_session(session_id, "agent:status", {
            "session_id": session_id,
            "status": "error",
            "session": session.model_dump(mode="json"),
        })
        return {
            "session_id": session_id,
            "browser_id": browser_id,
            "summary": f"Error: {error_text}",
            "action_log": [],
            "final_screenshot": None,
        }

    browser_tools = [
        ToolSchema(
            name=item["name"],
            description=item["description"],
            input_schema=item["input_schema"],
        )
        for item in BROWSER_TOOLS_SCHEMA
    ]
    history_key = (browser_id, provider_name)
    prior_messages = _browser_history.get(history_key) or []
    messages: list[ProviderMessage] = list(prior_messages)
    messages.append(provider.format_user_message(task))
    action_log: list[dict] = []
    final_screenshot: str | None = None

    # Loop detection state — sliding window of recent state-mutating tool calls
    recent_tool_calls: list[tuple[str, str, str]] = []
    loop_trigger_count = 0
    # Dead-card and stagnation state (see the guards above).
    card_gone_streak = 0
    card_gone = False
    stagnation_streak = 0
    prev_obs_url = ""
    prev_obs_text = ""

    user_msg = Message(role="user", content=task)
    session.messages.append(user_msg)
    await ws_manager.send_to_session(session_id, "agent:message", {
        "session_id": session_id,
        "message": user_msg.model_dump(mode="json"),
    })

    async def _cancellable(coro):
        """Race any awaitable against the cancel event. Returns None if cancelled."""
        task = asyncio.ensure_future(coro)
        cancel_wait = asyncio.ensure_future(cancel_event.wait())
        done, pending = await asyncio.wait(
            [task, cancel_wait], return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()
        if cancel_event.is_set():
            return None
        return task.result()

    text_parts = []  # initialized before loop so post-loop summary (line ~1294) has a default
    try:
        for turn in range(MAX_TURNS):
            if cancel_event.is_set():
                break

            response = await _cancellable(provider.create_message(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=browser_tools,
                messages=messages,
            ))
            if response is None:
                break
            # Guard against empty content (e.g. upstream API error that
            # the SDK parsed into a partial response object).
            if not response.content:
                logger.warning(f"Browser agent {session_id}: empty response content from {provider_name}/{model}")
                break

            # Track normalized usage from every provider adapter.
            if response.usage:
                session.tokens["input"] = session.tokens.get("input", 0) + response.usage.get("input_tokens", 0)
                session.tokens["output"] = session.tokens.get("output", 0) + response.usage.get("output_tokens", 0)

            text_parts = []
            tool_uses = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use" and block.tool_call:
                    tool_uses.append(block.tool_call)

            if text_parts:
                asst_msg = Message(
                    role="assistant",
                    content="\n".join(text_parts),
                )
                session.messages.append(asst_msg)
                await ws_manager.send_to_session(session_id, "agent:message", {
                    "session_id": session_id,
                    "message": asst_msg.model_dump(mode="json"),
                })

            for tu in tool_uses:
                tool_msg = Message(
                    role="tool_call",
                    content={"id": tu.id, "tool": tu.name, "input": tu.input},
                )
                session.messages.append(tool_msg)
                await ws_manager.send_to_session(session_id, "agent:message", {
                    "session_id": session_id,
                    "message": tool_msg.model_dump(mode="json"),
                })

            messages.append(provider.format_assistant_message(response))

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            cancelled = False

            # Sort tool_uses so ReportProgress is always processed first within
            # a turn, even if the model emits it after action tools. This way
            # the brain state is recorded before any actions execute.
            has_report_progress = any(tu.name == "ReportProgress" for tu in tool_uses)
            has_action_tools = any(
                tu.name in _ACTION_TOOLS_REQUIRING_REPORT for tu in tool_uses
            )
            # Violation: action tools without ReportProgress in the same turn.
            # The model MUST articulate its evaluation/memory/goal before acting.
            report_progress_violation = has_action_tools and not has_report_progress
            if report_progress_violation:
                logger.warning(
                    f"[browser-agent {session_id}] ReportProgress violation: "
                    f"action tools called without brain state"
                )
            # Stable sort: ReportProgress first, then everything else in order.
            tool_uses_sorted = sorted(
                tool_uses,
                key=lambda t: 0 if t.name == "ReportProgress" else 1,
            )

            for tu in tool_uses_sorted:
                if cancel_event.is_set():
                    cancelled = True
                    break

                # Handle ReportProgress — no-op execution that just records the
                # model's brain state and streams it to the dashboard.
                if tu.name == "ReportProgress":
                    eval_prev = tu.input.get("evaluation_previous", "")
                    working_mem = tu.input.get("working_memory", "")
                    next_goal = tu.input.get("next_goal", "")
                    brain_text = (
                        f"📋 **Plan**\n"
                        f"_Previous_: {eval_prev}\n"
                        f"_Memory_: {working_mem}\n"
                        f"_Next_: {next_goal}"
                    )
                    brain_msg = Message(role="assistant", content=brain_text)
                    session.messages.append(brain_msg)
                    await ws_manager.send_to_session(session_id, "agent:message", {
                        "session_id": session_id,
                        "message": brain_msg.model_dump(mode="json"),
                    })
                    tool_results.append(provider.format_tool_result(
                        tu.id, [{"type": "text", "text": "Progress recorded."}]
                    ))
                    continue

                # Reject action tools when ReportProgress is missing this turn.
                # We MUST still emit a tool_result for every tool_use_id or the
                # next API request 400s.
                if (
                    report_progress_violation
                    and tu.name in _ACTION_TOOLS_REQUIRING_REPORT
                ):
                    rejection_text = (
                        "REJECTED: You called an action tool without first calling "
                        "ReportProgress in the same turn. ReportProgress is REQUIRED "
                        "before every batch of action tools — it's how you reflect "
                        "on what just happened and articulate your next goal. Try "
                        "again: emit ReportProgress and your action tool(s) in the "
                        "same response."
                    )
                    tool_results.append(provider.format_tool_result(
                        tu.id, [{"type": "text", "text": rejection_text}]
                    ))
                    result_msg = Message(
                        role="tool_result",
                        content={
                            "text": rejection_text,
                            "tool_name": tu.name,
                            "elapsed_ms": 0,
                        },
                    )
                    session.messages.append(result_msg)
                    await ws_manager.send_to_session(session_id, "agent:message", {
                        "session_id": session_id,
                        "message": result_msg.model_dump(mode="json"),
                    })
                    continue

                # Handle RequestHumanIntervention — pause and wait for user
                if tu.name == "RequestHumanIntervention":
                    problem = tu.input.get("problem", "")
                    instruction = tu.input.get("instruction", "")
                    decision = await _request_browser_approval(
                        session, tu.name, {"problem": problem, "instruction": instruction},
                    )
                    if decision.get("behavior") != "deny":
                        result_text = "User resolved the issue. Continue with the task."
                    else:
                        user_message = decision.get("message", "").strip()
                        if user_message and user_message != "Skipped by user":
                            result_text = f"User skipped this intervention and said: \"{user_message}\"\nAddress what the user said and adapt your approach accordingly."
                        else:
                            result_text = "User skipped this intervention. Try a different approach or move on."
                    tool_results.append(provider.format_tool_result(
                        tu.id, [{"type": "text", "text": result_text}]
                    ))
                    result_msg = Message(
                        role="tool_result",
                        content={"text": result_text, "tool_name": tu.name, "elapsed_ms": 0},
                    )
                    session.messages.append(result_msg)
                    await ws_manager.send_to_session(session_id, "agent:message", {
                        "session_id": session_id,
                        "message": result_msg.model_dump(mode="json"),
                    })
                    continue

                # Handle RequestUserText — wait for the user's typed answer
                if tu.name == "RequestUserText":
                    question = tu.input.get("question", "")
                    context = tu.input.get("context", "")
                    decision = await _request_browser_approval(
                        session, tu.name, {"question": question, "context": context},
                    )
                    if decision.get("behavior") != "deny":
                        answer = (decision.get("message") or "").strip()
                        if answer:
                            result_text = f"User answered: \"{answer}\""
                        else:
                            result_text = "User acknowledged without typing an answer."
                    else:
                        result_text = (
                            "User cancelled instead of answering. "
                            "Proceed without the answer or try a different approach."
                        )
                    tool_results.append(provider.format_tool_result(
                        tu.id, [{"type": "text", "text": result_text}]
                    ))
                    result_msg = Message(
                        role="tool_result",
                        content={"text": result_text, "tool_name": tu.name, "elapsed_ms": 0},
                    )
                    session.messages.append(result_msg)
                    await ws_manager.send_to_session(session_id, "agent:message", {
                        "session_id": session_id,
                        "message": result_msg.model_dump(mode="json"),
                    })
                    continue

                policy = _browser_perms.get(tu.name, "always_allow")

                if policy == "deny":
                    denied_text = f"Tool {tu.name} is denied by permission policy."
                    tool_results.append(provider.format_tool_result(
                        tu.id, [{"type": "text", "text": denied_text}]
                    ))
                    result_msg = Message(
                        role="tool_result",
                        content={"text": denied_text, "tool_name": tu.name, "elapsed_ms": 0},
                    )
                    session.messages.append(result_msg)
                    await ws_manager.send_to_session(session_id, "agent:message", {
                        "session_id": session_id,
                        "message": result_msg.model_dump(mode="json"),
                    })
                    continue

                if policy == "ask":
                    decision = await _request_browser_approval(
                        session, tu.name, tu.input,
                    )
                    if decision.get("behavior") == "deny":
                        denied_text = decision.get("message") or f"Tool {tu.name} denied by user."
                        tool_results.append(provider.format_tool_result(
                            tu.id, [{"type": "text", "text": denied_text}]
                        ))
                        result_msg = Message(
                            role="tool_result",
                            content={"text": denied_text, "tool_name": tu.name, "elapsed_ms": 0},
                        )
                        session.messages.append(result_msg)
                        await ws_manager.send_to_session(session_id, "agent:message", {
                            "session_id": session_id,
                            "message": result_msg.model_dump(mode="json"),
                        })
                        continue

                start = time.time()
                result = await _cancellable(execute_browser_tool(
                    tu.name, tu.input, browser_id, tab_id,
                ))
                if result is None:
                    cancelled = True
                    break
                elapsed_ms = int((time.time() - start) * 1000)

                action_log.append({
                    "tool": tu.name,
                    "input": tu.input,
                    "result_summary": result.get("text", result.get("error", ""))[:200],
                    "elapsed_ms": elapsed_ms,
                    # execute_browser_tool reports failure as an "error" key, so
                    # this is the structural success signal the honesty gate uses.
                    "ok": "error" not in result,
                })

                if tu.name == "BrowserScreenshot" and result.get("image"):
                    final_screenshot = result["image"]

                # Loop detection: did we just repeat the same (tool, input,
                # result) for the third time in a row? If so, attach a loud
                # warning to this tool_result so the model is forced to
                # acknowledge it on its next turn.
                call_key = _hash_tool_call(tu.name, tu.input, result)
                is_loop = _detect_loop(recent_tool_calls, call_key)
                if call_key[0] not in _LOOP_DETECTION_EXCLUDED_TOOLS:
                    recent_tool_calls.append(call_key)
                    if len(recent_tool_calls) > _LOOP_WINDOW_SIZE * 2:
                        recent_tool_calls = recent_tool_calls[-_LOOP_WINDOW_SIZE * 2:]

                content_blocks = _format_tool_result(result, tu.name)
                if is_loop:
                    loop_trigger_count += 1
                    repeat_count = sum(1 for c in recent_tool_calls if c == call_key)
                    warning = _LOOP_WARNING_TEXT.format(count=repeat_count)
                    logger.warning(
                        f"[browser-agent {session_id}] loop detected on {tu.name} "
                        f"(trigger #{loop_trigger_count}): {warning}"
                    )
                    content_blocks = content_blocks + [
                        {"type": "text", "text": f"\n\n⚠️ {warning}"}
                    ]

                # Stagnation: state-mutating actions that change nothing and keep
                # looking like failures. Nudge at the escalation thresholds so the
                # model revises its plan instead of cycling selectors.
                stagnation_streak, prev_obs_url, prev_obs_text, nudge = advance_stagnation(
                    stagnation_streak, prev_obs_url, prev_obs_text, tu.name, result,
                )
                if nudge:
                    logger.warning(
                        f"[browser-agent {session_id}] stagnation streak "
                        f"{stagnation_streak} on {tu.name}"
                    )
                    content_blocks = content_blocks + [
                        {"type": "text", "text": f"\n\n⚠️ {nudge}"}
                    ]

                tool_results.append(provider.format_tool_result(tu.id, content_blocks))

                result_text = result.get("text", result.get("error", ""))
                result_msg = Message(
                    role="tool_result",
                    content={"text": result_text, "tool_name": tu.name, "elapsed_ms": elapsed_ms},
                )
                session.messages.append(result_msg)
                await ws_manager.send_to_session(session_id, "agent:message", {
                    "session_id": session_id,
                    "message": result_msg.model_dump(mode="json"),
                })

                # Dead card: a sustained pattern means the browser is gone or
                # wedged, so retrying only burns the rest of the turn budget.
                if card_is_unavailable(result):
                    card_gone_streak += 1
                    if card_gone_streak >= CARD_GONE_LIMIT:
                        logger.warning(
                            f"[browser-agent {session_id}] browser card "
                            f"{browser_id} is unavailable — failing fast"
                        )
                        card_gone = True
                        break
                else:
                    card_gone_streak = 0

            messages.append(ProviderMessage(role="tool_result", content=tool_results))

            if cancelled:
                break

            if card_gone:
                break

            # Hard cap on loops: if the model keeps repeating itself even
            # after we warn it, force-exit so we don't burn the entire turn
            # budget on a stuck agent.
            if loop_trigger_count >= _LOOP_HARD_CAP:
                logger.warning(
                    f"[browser-agent {session_id}] hit loop hard cap "
                    f"({_LOOP_HARD_CAP}) — force-exiting"
                )
                break

        if cancel_event.is_set():
            session.status = "stopped"
            await ws_manager.send_to_session(session_id, "agent:status", {
                "session_id": session_id,
                "status": "stopped",
                "session": session.model_dump(mode="json"),
            })
            return {
                "session_id": session_id,
                "browser_id": browser_id,
                "summary": "Agent was stopped by the user. Do NOT retry or create new browser agents.",
                "error": "Agent was stopped by the user.",
                "action_log": action_log,
                "final_screenshot": final_screenshot,
            }

        summary_parts = text_parts if text_parts else ["Task completed."]
        summary = "\n".join(summary_parts)

        if not final_screenshot:
            try:
                ss_result = await execute_browser_tool(
                    "BrowserScreenshot", {}, browser_id, tab_id,
                )
                if ss_result.get("image"):
                    final_screenshot = ss_result["image"]
            except Exception:
                pass

        # Keep provider-specific history so future work on this browser can
        # resume without mixing Anthropic/OpenAI/Ollama message formats.
        _browser_history[history_key] = _trim_provider_history(
            messages, _MAX_HISTORY_MESSAGES,
        )

        # A model that ends its turn is not proof the goal happened. Reality-check
        # before the status is allowed to say "completed".
        honest, reason = completion_is_honest(action_log)
        if not honest:
            error_text = f"Browser agent finished without evidence of success: {reason}."
            logger.warning(f"[browser-agent {session_id}] {error_text}")
            session.status = "error"
            err_msg = Message(role="system", content=f"Error: {error_text}")
            session.messages.append(err_msg)
            await ws_manager.send_to_session(session_id, "agent:message", {
                "session_id": session_id,
                "message": err_msg.model_dump(mode="json"),
            })
            await ws_manager.send_to_session(session_id, "agent:status", {
                "session_id": session_id,
                "status": "error",
                "session": session.model_dump(mode="json"),
            })
            return {
                "session_id": session_id,
                "browser_id": browser_id,
                "summary": summary,
                "error": error_text,
                "action_log": action_log,
                "final_screenshot": final_screenshot,
            }

        session.status = "completed"
        agent_manager._fire_session_completed(session)
        await ws_manager.send_to_session(session_id, "agent:status", {
            "session_id": session_id,
            "status": "completed",
            "session": session.model_dump(mode="json"),
        })

        return {
            "session_id": session_id,
            "browser_id": browser_id,
            "summary": summary,
            "action_log": action_log,
            "final_screenshot": final_screenshot,
        }

    except Exception as e:
        logger.exception(f"Browser agent {session_id} error: {e}")
        session.status = "error"
        error_msg = Message(role="system", content=f"Error: {str(e)}")
        session.messages.append(error_msg)
        await ws_manager.send_to_session(session_id, "agent:message", {
            "session_id": session_id,
            "message": error_msg.model_dump(mode="json"),
        })
        await ws_manager.send_to_session(session_id, "agent:status", {
            "session_id": session_id,
            "status": "error",
            "session": session.model_dump(mode="json"),
        })

        return {
            "session_id": session_id,
            "browser_id": browser_id,
            "summary": f"Error: {str(e)}",
            "action_log": action_log,
            "final_screenshot": None,
        }
    finally:
        close = getattr(provider, "close", None)
        if close:
            await close()


async def _create_browser_card(dashboard_id: str, url: str, parent_session_id: str | None = None) -> str:
    """Create a new browser card on the dashboard and return its browser_id."""
    from backend.apps.dashboards.dashboards import _load, _save
    from backend.apps.dashboards.models import BrowserCardPosition, BrowserTab

    dashboard = _load(dashboard_id)
    browser_id = f"browser-{uuid4().hex[:8]}"
    tab_id = f"tab-{uuid4().hex[:8]}"
    tab = BrowserTab(id=tab_id, url=url or "https://www.google.com", title="")
    card = BrowserCardPosition(
        browser_id=browser_id,
        url=url or "https://www.google.com",
        tabs=[tab],
        activeTabId=tab_id,
        x=40,
        y=100,
        width=1280,
        height=800,
    )
    dashboard.layout.browser_cards[browser_id] = card
    dashboard.updated_at = datetime.now()
    _save(dashboard)

    await ws_manager.broadcast_global("dashboard:browser_card_added", {
        "dashboard_id": dashboard_id,
        "browser_card": card.model_dump(mode="json"),
        "parent_session_id": parent_session_id or "",
    })
    return browser_id


async def run_browser_agents(
    tasks: list[dict],
    model: str,
    dashboard_id: str | None = None,
    pre_selected_browser_ids: list[str] | None = None,
    parent_session_id: str | None = None,
) -> list[dict]:
    """Run multiple browser sub-agents in parallel.

    Each task dict has: { browser_id (optional), task, url (optional) }
    Returns a list of result dicts, one per task.
    """
    from backend.apps.analytics.collector import record as _analytics
    _analytics("feature.used", {
        "feature": "browser_agent.launched",
        "task_count": len(tasks),
        "model": model,
    }, dashboard_id=dashboard_id)

    pre_selected = set(pre_selected_browser_ids or [])

    async def _run_one(task_def: dict) -> dict:
        browser_id = task_def.get("browser_id", "")
        task_text = task_def.get("task", "")
        url = task_def.get("url", "")

        if not browser_id and dashboard_id:
            browser_id = await _create_browser_card(dashboard_id, url, parent_session_id)
            await asyncio.sleep(2.0)

        is_pre_selected = browser_id in pre_selected
        return await run_browser_agent(
            task=task_text,
            browser_id=browser_id,
            model=model,
            dashboard_id=dashboard_id,
            pre_selected=is_pre_selected,
            initial_url=url if url and browser_id not in pre_selected else None,
            parent_session_id=parent_session_id,
        )

    results = await asyncio.gather(*[_run_one(t) for t in tasks], return_exceptions=True)

    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append({"summary": f"Error: {str(r)}", "action_log": [], "final_screenshot": None})
        else:
            final.append(r)
    return final
