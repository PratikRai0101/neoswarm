"""Web tools: WebSearch and WebFetch."""

from __future__ import annotations

import asyncio
import html
import re
import time
from typing import Any
from urllib.parse import quote_plus, unquote

import httpx

from backend.apps.agents.tools.base import BaseTool, ToolContext

_MAX_OUTPUT_BYTES = 100 * 1024  # ~100 KB
_MAX_SEARCH_BYTES = 20 * 1024  # search results stay small enough for prompts
_HTTP_TIMEOUT = 30  # seconds
_SEARCH_BUDGET = 30.0  # whole-race wall clock; no engine can starve the rest
_HEDGE_AFTER = 1.5  # a healthy frontend answers in ~1s; slower means start the next engine
_FAILURES_TO_OPEN = 3  # consecutive failures before an engine is benched
_FIRST_COOLDOWN = 120.0
_MAX_COOLDOWN = 900.0
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Per-engine circuit breaker: {name: {"failures": int, "open_until": float, "cooldown": float}}
_tier_health: dict[str, dict[str, float]] = {}


def _tier_cooldown_left(name: str) -> float:
    entry = _tier_health.get(name)
    if not entry:
        return 0.0
    return max(0.0, entry["open_until"] - time.monotonic())


def _record_tier_success(name: str) -> None:
    _tier_health.pop(name, None)


def _record_tier_failure(name: str, *, conclusive: bool = False) -> None:
    entry = _tier_health.setdefault(name, {"failures": 0.0, "open_until": 0.0, "cooldown": 0.0})
    entry["failures"] += 1
    if not conclusive and entry["failures"] < _FAILURES_TO_OPEN:
        return
    entry["cooldown"] = min(max(entry["cooldown"] * 2, _FIRST_COOLDOWN), _MAX_COOLDOWN)
    entry["open_until"] = time.monotonic() + entry["cooldown"]


def reset_search_tier_health() -> None:
    _tier_health.clear()


def _truncate(text: str, limit: int = _MAX_OUTPUT_BYTES) -> str:
    if len(text) > limit:
        return text[:limit] + "\n... (output truncated)"
    return text


def _strip_html(raw_html: str) -> str:
    """Naive but effective HTML → plain-text conversion."""
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ───────────────────────────────────────────────────────────────────────────
# WebSearchTool
# ───────────────────────────────────────────────────────────────────────────


class WebSearchTool(BaseTool):
    name = "WebSearch"
    description = (
        "Search the web using DuckDuckGo and return titles, URLs, and "
        "snippets for the top results."
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        query: str = input_data["query"]
        num_results: int = max(1, min(input_data.get("num_results", 5), 10))

        results, errors = await _race_search(query, num_results)
        if results:
            return [{"type": "text", "text": results}]
        detail = f"No search results found for: {query}"
        if errors:
            detail += f" ({'; '.join(errors)})"
        return [{"type": "text", "text": detail}]

    @staticmethod
    async def _search_ddg(query: str, num_results: int) -> str:
        """Query DuckDuckGo HTML endpoint and parse results."""
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            resp.raise_for_status()

        body = resp.text

        # Parse result blocks – DuckDuckGo wraps each result in
        # <div class="result ..."> ... </div>
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</div>\s*(?=<div[^>]*class="[^"]*result|$)',
            body,
            flags=re.DOTALL,
        )

        entries: list[str] = []
        for block in result_blocks:
            if len(entries) >= num_results:
                break

            # Title + URL — handle both class-before-href and href-before-class
            link_match = re.search(
                r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                block,
                flags=re.DOTALL,
            )
            if not link_match:
                # Try reversed attribute order
                link_match = re.search(
                    r'<a[^>]*href="([^"]*)"[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>',
                    block,
                    flags=re.DOTALL,
                )
            if not link_match:
                continue

            raw_url = html.unescape(link_match.group(1))
            title = _strip_html(link_match.group(2)).strip()

            # Snippet
            snippet_match = re.search(
                r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                block,
                flags=re.DOTALL,
            )
            snippet = _strip_html(snippet_match.group(1)).strip() if snippet_match else ""

            # DuckDuckGo wraps URLs through a redirect; try to extract the real URL
            real_url_match = re.search(r"uddg=([^&]+)", raw_url)
            if real_url_match:
                from urllib.parse import unquote
                url = unquote(real_url_match.group(1))
            else:
                url = raw_url

            entry = f"[{len(entries) + 1}] {title}\n    {url}"
            if snippet:
                entry += f"\n    {snippet}"
            entries.append(entry)

        return "\n\n".join(entries)


async def _search_bing(query: str, num_results: int) -> str:
    """Query Bing's RSS endpoint and format results like the DDG engine."""
    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = await client.get(
            f"https://www.bing.com/search?q={quote_plus(query)}&format=rss"
        )
        resp.raise_for_status()

    items = re.findall(r"<item>(.*?)</item>", resp.text, flags=re.DOTALL | re.IGNORECASE)
    entries: list[str] = []
    for item in items:
        if len(entries) >= num_results:
            break
        title_match = re.search(r"<title>(.*?)</title>", item, flags=re.DOTALL | re.IGNORECASE)
        link_match = re.search(r"<link>(.*?)</link>", item, flags=re.DOTALL | re.IGNORECASE)
        desc_match = re.search(
            r"<description>(.*?)</description>", item, flags=re.DOTALL | re.IGNORECASE
        )
        if not title_match or not link_match:
            continue
        title = _strip_html(title_match.group(1)).strip()
        url = html.unescape(link_match.group(1)).strip()
        snippet = _strip_html(desc_match.group(1)).strip() if desc_match else ""
        entry = f"[{len(entries) + 1}] {title}\n    {url}"
        if snippet:
            entry += f"\n    {snippet}"
        entries.append(entry)
    return "\n\n".join(entries)


async def _search_brave(query: str, num_results: int) -> str:
    """Best-effort Brave search scrape. Returns "" on parse misses (fall
    through) and raises on transport failures (counted by the breaker)."""
    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
    ) as client:
        resp = await client.get(f"https://search.brave.com/search?q={quote_plus(query)}")
        resp.raise_for_status()

    body = resp.text
    # Brave renders web results as anchors with result URLs plus nearby
    # description divs; extract (url, title) pairs conservatively.
    anchors = re.findall(
        r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', body, flags=re.DOTALL
    )
    entries: list[str] = []
    seen: set[str] = set()
    for url, title_html in anchors:
        if len(entries) >= num_results:
            break
        if "brave.com" in url or url in seen:
            continue
        title = _strip_html(title_html).strip()
        if len(title) < 8 or len(title) > 200:
            continue
        seen.add(url)
        entries.append(f"[{len(entries) + 1}] {title}\n    {html.unescape(url)}")
    return "\n\n".join(entries)


async def _race_search(query: str, num_results: int) -> tuple[str | None, list[str]]:
    """Race keyless engines; the first good answer wins.

    The next engine starts when the leader is SLOW (not only when it fails),
    so one dead frontend costs the hedge delay instead of its full budget.
    Output contains only result lines — never leaked presentation
    instructions — and is bounded so large result sets fit in prompts.
    """
    engines = [
        ("ddg", lambda: WebSearchTool._search_ddg(query, num_results)),
        ("bing", lambda: _search_bing(query, num_results)),
        ("brave", lambda: _search_brave(query, num_results)),
    ]
    live = []
    errors: list[str] = []
    for name, run in engines:
        cooling = _tier_cooldown_left(name)
        if cooling:
            errors.append(f"{name}: skipped, still failing (retry in {cooling:.0f}s)")
        else:
            live.append((name, run))
    if not live:
        return None, errors

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _SEARCH_BUDGET
    running: dict[asyncio.Task, str] = {}
    started: dict[str, float] = {}
    next_engine = 0

    def _start_next() -> None:
        nonlocal next_engine
        name, run = live[next_engine]
        next_engine += 1
        started[name] = loop.time()
        running[asyncio.ensure_future(run())] = name

    _start_next()
    result: str | None = None

    while running and result is None:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        wait_for = remaining
        if next_engine < len(live):
            oldest = min(started[name] for name in running.values())
            wait_for = min(wait_for, max(0.0, oldest + _HEDGE_AFTER - loop.time()))
        done, _ = await asyncio.wait(set(running), timeout=wait_for,
                                     return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            name = running.pop(task)
            try:
                answer = task.result()
            except asyncio.CancelledError:
                continue
            except Exception as exc:
                errors.append(f"{name}: {str(exc)[:150]}")
                _record_tier_failure(name)
                continue
            _record_tier_success(name)
            if answer and result is None:
                result = answer
        if result is None and next_engine < len(live) and (not done or not running):
            _start_next()

    for task, name in list(running.items()):
        task.cancel()
        silent_for = loop.time() - started[name]
        if silent_for >= _HEDGE_AFTER:
            errors.append(f"{name}: no response in {silent_for:.0f}s")
            _record_tier_failure(name, conclusive=True)
    if running:
        await asyncio.gather(*running, return_exceptions=True)

    if result and len(result) > _MAX_SEARCH_BYTES:
        result = result[:_MAX_SEARCH_BYTES] + "\n... (search results truncated)"
    return result, errors


# ───────────────────────────────────────────────────────────────────────────
# WebFetchTool
# ───────────────────────────────────────────────────────────────────────────


class WebFetchTool(BaseTool):
    name = "WebFetch"
    description = (
        "Fetch the contents of a URL and return the extracted text. "
        "HTML is stripped to plain text. Output is truncated to ~100 KB."
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Optional prompt/context describing what information to look for.",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        url: str = input_data["url"]
        prompt: str | None = input_data.get("prompt")

        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return [{"type": "text", "text": f"HTTP error {exc.response.status_code} fetching {url}"}]
        except Exception as exc:
            return [{"type": "text", "text": f"Error fetching {url}: {exc}"}]

        content_type = resp.headers.get("content-type", "")

        if "html" in content_type or resp.text.strip().startswith("<!"):
            text = _strip_html(resp.text)
        else:
            text = resp.text

        text = _truncate(text)

        header = f"Contents of {url}:"
        if prompt:
            header += f"\n(Looking for: {prompt})"

        return [{"type": "text", "text": f"{header}\n\n{text}"}]
