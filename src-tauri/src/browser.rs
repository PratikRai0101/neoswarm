//! Native browser-control primitives for Tauri child webviews.
//!
//! Interface contract (frozen — the frontend binds to these signatures):
//!
//! Every command takes `label: String` as its first argument and resolves the
//! target webview with [`get_webview`], so a missing webview produces the same
//! `Browser webview '<label>' was not found` string error the existing browser
//! commands use. Every command has a `Result<serde_json::Value, String>` return
//! type, so successes are JSON serializable and failures are String errors
//! instead of panics.
//!
//! - `browser_click(label: String, selector: String)`
//!     -> `{ "text": String, "url": String, "clickX": number, "clickY": number }`
//!        or `{ "error": String }`
//!        `clickX`/`clickY` are percentages in `[0, 100]` of the viewport.
//! - `browser_type(label: String, selector: String, text: String)`
//!     -> `{ "text": String, "url": String }` or `{ "error": String }`
//! - `browser_scroll(label: String, direction: String, amount: number)`
//!     -> `{ "text": String, "scrolled": number, "scrollTop": number,
//!          "scrollHeight": number, "clientHeight": number, "atTop": bool,
//!          "atBottom": bool, "target": String, "url": String }`
//!        or `{ "error": String }`
//!        `direction` is `"up"` or `"down"` (anything else is treated as down).
//! - `browser_press_key(label: String, key: String)`
//!     -> `{ "text": String, "url": String }` or `{ "error": String }`
//! - `browser_screenshot(label: String)`
//!     -> `{ "image": String, "url": String }` or `{ "error": String }`
//!        `image` is base64-encoded PNG data without a `data:` prefix.
//! - `browser_get_text(label: String, selector: String)`
//!     -> `{ "text": String, "url": String, "title": String }`
//!        or `{ "error": String }`
//!        An empty `selector` reads the whole document body.
//! - `browser_get_elements(label: String)`
//!     -> `{ "text": String, "elements": Array<{
//!            "selector": String, "tag": String, "type": String|null,
//!            "text": String|null, "placeholder": String|null,
//!            "ariaLabel": String|null, "role": String|null,
//!            "href": String|null }>,
//!          "total": number, "url": String, "title": String }`
//!        or `{ "error": String }`
//! - `browser_list_interactives(label: String)`
//!     -> `{ "text": String, "elements": Array<{
//!            "index": number, "role": String, "name": String }>,
//!          "url": String }`
//!        or `{ "error": String }`
//! - `browser_click_index(label: String, selector: String, index: number)`
//!     -> `{ "text": String, "url": String, "clickX": number, "clickY": number }`
//!        or `{ "error": String }`
//!        `selector` scopes the interactive-element query (`""` or `"body"` for
//!        the whole document); `index` is 1-based and matches the index produced
//!        by `browser_list_interactives`. `clickX`/`clickY` are percentages.
//! - `browser_wait(label: String, milliseconds: number)`
//!     -> `{ "text": String, "url": String, "title": String }`
//!        `milliseconds` is clamped to `[1, 30000]`; invalid values become 500.
//!
//! The existing `browser_eval`, `browser_navigate`, `browser_reload`,
//! `browser_history`, and `browser_url` commands are unchanged.
//!
//! Implementation note: the DOM-based commands (`browser_click`,
//! `browser_type`, `browser_scroll`, `browser_press_key`, `browser_get_text`,
//! `browser_get_elements`, `browser_list_interactives`, `browser_click_index`)
//! execute their DOM logic inside the target webview, because Tauri/wry exposes
//! no native DOM or input-dispatch API. `browser_screenshot` is different: it is
//! captured natively on macOS (via `/usr/sbin/screencapture`) without running
//! any JavaScript.

use serde_json::{json, Value};
use tauri::{AppHandle, Manager};
use url::Url;

fn get_webview(app: &AppHandle, label: &str) -> Result<tauri::Webview<tauri::Wry>, String> {
    app.get_webview(label)
        .ok_or_else(|| format!("Browser webview '{label}' was not found"))
}

#[tauri::command]
pub async fn browser_eval(
    app: AppHandle,
    label: String,
    script: String,
) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    let (sender, mut receiver) = tauri::async_runtime::channel(1);
    webview
        .eval_with_callback(script, move |result| {
            let _ = sender.try_send(result);
        })
        .map_err(|error| format!("Failed to evaluate browser script: {error}"))?;

    let result = receiver
        .recv()
        .await
        .ok_or_else(|| "Browser evaluation returned no result".to_string())?;
    Ok(serde_json::from_str(&result).unwrap_or_else(|_| Value::String(result)))
}

#[tauri::command]
pub fn browser_navigate(app: AppHandle, label: String, url: String) -> Result<(), String> {
    let webview = get_webview(&app, &label)?;
    let parsed = Url::parse(&url).map_err(|error| format!("Invalid browser URL: {error}"))?;
    webview
        .navigate(parsed)
        .map_err(|error| format!("Failed to navigate browser: {error}"))
}

#[tauri::command]
pub fn browser_reload(app: AppHandle, label: String) -> Result<(), String> {
    get_webview(&app, &label)?
        .reload()
        .map_err(|error| format!("Failed to reload browser: {error}"))
}

#[tauri::command]
pub fn browser_history(app: AppHandle, label: String, direction: String) -> Result<(), String> {
    let script = match direction.as_str() {
        "back" => "history.back(); true;",
        "forward" => "history.forward(); true;",
        _ => return Err("Browser history direction must be 'back' or 'forward'".to_string()),
    };
    get_webview(&app, &label)?
        .eval(script)
        .map_err(|error| format!("Failed to move browser history: {error}"))
}

#[tauri::command]
pub fn browser_url(app: AppHandle, label: String) -> Result<String, String> {
    get_webview(&app, &label)
        .and_then(|webview| webview.url().map(|url| url.to_string()).map_err(|error| error.to_string()))
}

/// Run `script` on `webview` and parse the JSON-serialized result.
///
/// The completion callback always fires for plain object/string/number results;
/// scripts wrap their body in `try/catch` so JS failures come back as JSON
/// `{ "error": ... }` objects rather than empty callbacks.
async fn eval_json(webview: &tauri::Webview<tauri::Wry>, script: String) -> Result<Value, String> {
    let (sender, mut receiver) = tauri::async_runtime::channel(1);
    webview
        .eval_with_callback(script, move |result| {
            let _ = sender.try_send(result);
        })
        .map_err(|error| format!("Failed to evaluate browser script: {error}"))?;

    let result = receiver
        .recv()
        .await
        .ok_or_else(|| "Browser evaluation returned no result".to_string())?;
    Ok(serde_json::from_str(&result).unwrap_or_else(|_| Value::String(result)))
}

/// JSON-encode a string so it can be embedded safely in a JS script.
fn script_literal(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".to_string())
}

/// JSON-encode a finite number literal, falling back to `fallback`.
fn number_literal(value: f64, fallback: f64) -> String {
    let value = if value.is_finite() { value } else { fallback };
    serde_json::to_string(&value).unwrap_or_else(|_| fallback.to_string())
}

/// Substitute `__NEOSWARM_*__` placeholders in a script template.
fn render_script(template: &str, values: &[(&str, String)]) -> String {
    values.iter().fold(template.to_string(), |script, (token, value)| {
        script.replace(token, value)
    })
}

const CLICK_SCRIPT: &str = r#"(() => {
  try {
    const selector = __NEOSWARM_SELECTOR__;
    const el = document.querySelector(selector);
    if (!el) return { error: 'Element not found: ' + selector };
    el.scrollIntoView({ block: 'center' });
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const opts = { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 };
    if (typeof PointerEvent === 'function') {
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1 }));
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1 }));
    }
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
    return {
      text: 'Clicked element: ' + el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
      url: location.href,
      clickX: window.innerWidth > 0 ? (x / window.innerWidth) * 100 : 50,
      clickY: window.innerHeight > 0 ? (y / window.innerHeight) * 100 : 50,
    };
  } catch (error) {
    return { error: 'Click failed: ' + String(error) };
  }
})()"#;

const TYPE_SCRIPT: &str = r#"(() => {
  try {
    const selector = __NEOSWARM_SELECTOR__;
    const text = __NEOSWARM_TEXT__;
    const el = document.querySelector(selector);
    if (!el) return { error: 'Element not found: ' + selector };
    el.scrollIntoView({ block: 'center' });
    el.focus();
    if (el.select) el.select();
    if ('value' in el) {
      el.value = text;
    } else {
      el.textContent = text;
    }
    el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: text }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return {
      text: 'Typed into: ' + el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
      url: location.href,
    };
  } catch (error) {
    return { error: 'Type failed: ' + String(error) };
  }
})()"#;

const SCROLL_SCRIPT: &str = r#"(() => {
  try {
    function findScrollable() {
      const candidates = document.querySelectorAll('[class*="scroller"], [class*="scroll-container"], [class*="content"], main, [role="main"], article');
      for (const el of candidates) {
        const style = window.getComputedStyle(el);
        const scrollable = style.overflow === 'auto' || style.overflow === 'scroll'
          || style.overflowY === 'auto' || style.overflowY === 'scroll';
        if (scrollable && el.scrollHeight > el.clientHeight + 10) return el;
      }
      const all = document.querySelectorAll('*');
      for (const el of all) {
        if (el === document.body || el === document.documentElement) continue;
        const style = window.getComputedStyle(el);
        const scrollable = style.overflow === 'auto' || style.overflow === 'scroll'
          || style.overflowY === 'auto' || style.overflowY === 'scroll';
        if (scrollable && el.scrollHeight > el.clientHeight + 50 && el.clientHeight > 200) return el;
      }
      return null;
    }
    const direction = __NEOSWARM_DIRECTION__;
    const amount = __NEOSWARM_AMOUNT__;
    const delta = direction === 'up' ? -amount : amount;
    const container = findScrollable();
    if (container) {
      const before = container.scrollTop;
      container.scrollBy({ top: delta, behavior: 'instant' });
      const after = container.scrollTop;
      return {
        text: 'Scrolled ' + direction + ' by ' + Math.abs(after - before) + 'px',
        scrolled: Math.abs(after - before),
        scrollTop: after,
        scrollHeight: container.scrollHeight,
        clientHeight: container.clientHeight,
        atTop: after <= 0,
        atBottom: after + container.clientHeight >= container.scrollHeight - 5,
        target: 'container',
        url: location.href,
      };
    }
    const before = window.scrollY;
    window.scrollBy({ top: delta, behavior: 'instant' });
    const after = window.scrollY;
    return {
      text: 'Scrolled ' + direction + ' by ' + Math.abs(after - before) + 'px',
      scrolled: Math.abs(after - before),
      scrollTop: after,
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: window.innerHeight,
      atTop: after <= 0,
      atBottom: after + window.innerHeight >= document.documentElement.scrollHeight - 5,
      target: 'window',
      url: location.href,
    };
  } catch (error) {
    return { error: 'Scroll failed: ' + String(error) };
  }
})()"#;

const PRESS_KEY_SCRIPT: &str = r#"(() => {
  try {
    const key = __NEOSWARM_KEY__;
    const target = document.activeElement || document.body || document.documentElement;
    if (!target) return { error: 'No element available to receive the key press' };
    const options = { key: key, code: key, bubbles: true, cancelable: true };
    target.dispatchEvent(new KeyboardEvent('keydown', options));
    target.dispatchEvent(new KeyboardEvent('keypress', options));
    target.dispatchEvent(new KeyboardEvent('keyup', options));
    return { text: 'Pressed ' + key, url: location.href };
  } catch (error) {
    return { error: 'Press key failed: ' + String(error) };
  }
})()"#;

const GET_TEXT_SCRIPT: &str = r#"(() => {
  try {
    const selector = __NEOSWARM_SELECTOR__;
    const root = selector ? document.querySelector(selector) : document.body;
    if (!root) return { error: 'Element not found: ' + selector, url: location.href, title: document.title };
    const text = root.innerText || root.textContent || '';
    return {
      text: text.substring(0, 15000),
      url: location.href,
      title: document.title,
    };
  } catch (error) {
    return { error: 'Get text failed: ' + String(error) };
  }
})()"#;

const GET_ELEMENTS_SCRIPT: &str = r#"(() => {
  try {
    const interactive = document.querySelectorAll(
      'a[href], button, input, textarea, select, [role="button"], [role="link"], '
      + '[role="textbox"], [role="searchbox"], [role="menuitem"], [role="tab"], '
      + '[role="checkbox"], [role="switch"], [role="option"], '
      + '[onclick], [tabindex]:not([tabindex="-1"]), [contenteditable="true"]'
    );
    const seen = {};
    const results = [];
    for (const el of interactive) {
      if (results.length >= 80) break;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      const style = window.getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;

      let selector = el.tagName.toLowerCase();
      if (el.id) {
        selector = '#' + CSS.escape(el.id);
      } else if (el.getAttribute('name')) {
        selector = el.tagName.toLowerCase() + '[name="' + CSS.escape(el.getAttribute('name')) + '"]';
      } else if (el.getAttribute('aria-label')) {
        selector = el.tagName.toLowerCase() + '[aria-label="' + CSS.escape(el.getAttribute('aria-label')) + '"]';
      } else if (el.getAttribute('type') && el.tagName === 'INPUT') {
        selector = 'input[type="' + el.getAttribute('type') + '"]';
        if (el.getAttribute('placeholder')) {
          selector += '[placeholder="' + CSS.escape(el.getAttribute('placeholder')) + '"]';
        }
      } else if (el.className && typeof el.className === 'string') {
        const cls = el.className.trim().split(/\s+/)[0];
        if (cls && cls.length < 60) selector = el.tagName.toLowerCase() + '.' + CSS.escape(cls);
      }

      if (seen[selector]) {
        const parent = el.parentElement;
        if (parent && parent.id) {
          selector = '#' + CSS.escape(parent.id) + ' > ' + selector;
        } else {
          const siblings = parent ? Array.from(parent.children) : [];
          const index = siblings.indexOf(el);
          if (index >= 0) selector += ':nth-child(' + (index + 1) + ')';
        }
      }
      seen[selector] = true;

      results.push({
        selector: selector,
        tag: el.tagName.toLowerCase(),
        type: el.type ? String(el.type) : null,
        text: (el.textContent || '').trim().substring(0, 120) || null,
        placeholder: el.placeholder ? String(el.placeholder) : null,
        ariaLabel: el.getAttribute('aria-label') || null,
        role: el.getAttribute('role') || null,
        href: el.href ? String(el.href) : null,
      });
    }
    const payload = {
      elements: results,
      total: interactive.length,
      url: location.href,
      title: document.title,
    };
    payload.text = JSON.stringify(payload, null, 2);
    return payload;
  } catch (error) {
    return { error: 'Get elements failed: ' + String(error) };
  }
})()"#;

const LIST_INTERACTIVES_SCRIPT: &str = r#"(() => {
  try {
    const nodes = document.querySelectorAll(
      'a, button, input, textarea, select, [role="button"], [role="link"], '
      + '[role="textbox"], [role="searchbox"], [role="menuitem"], [role="tab"], '
      + '[role="checkbox"], [role="switch"], [role="option"], '
      + '[tabindex]:not([tabindex="-1"]), [contenteditable="true"]'
    );
    const elements = [];
    let index = 1;
    for (const el of nodes) {
      if (el.disabled) continue;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      if (elements.length >= 100) break;
      const role = el.getAttribute('role') || el.tagName.toLowerCase();
      const name = (el.getAttribute('aria-label') || el.innerText || el.placeholder || el.value || '')
        .trim()
        .substring(0, 80);
      elements.push({ index: index, role: role, name: name });
      index += 1;
    }
    const text = elements.length
      ? elements.length + ' interactive elements:\n' + elements.map(function (el) {
          return '[' + el.index + ']<' + el.role + ' "' + el.name + '">';
        }).join('\n')
      : 'No interactive elements found on this page.';
    return { text: text, elements: elements, url: location.href };
  } catch (error) {
    return { error: 'List interactives failed: ' + String(error) };
  }
})()"#;

const CLICK_INDEX_SCRIPT: &str = r#"(() => {
  try {
    const selector = __NEOSWARM_SELECTOR__;
    const index = __NEOSWARM_INDEX__;
    const scoped = selector && selector !== 'body' ? document.querySelector(selector) : document;
    const root = scoped || document;
    const nodes = root.querySelectorAll(
      'a, button, input, textarea, select, [role="button"], [role="link"], '
      + '[role="textbox"], [role="searchbox"], [role="menuitem"], [role="tab"], '
      + '[role="checkbox"], [role="switch"], [role="option"], '
      + '[tabindex]:not([tabindex="-1"]), [contenteditable="true"]'
    );
    const visible = [];
    for (const el of nodes) {
      if (el.disabled) continue;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      visible.push(el);
    }
    const el = visible[index - 1];
    if (!el) return { error: 'Index ' + index + ' is not available (' + visible.length + ' interactive elements found)' };
    el.scrollIntoView({ block: 'center' });
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const opts = { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 };
    if (typeof PointerEvent === 'function') {
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1 }));
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1 }));
    }
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
    return {
      text: 'Clicked index ' + index + ': ' + el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
      url: location.href,
      clickX: window.innerWidth > 0 ? (x / window.innerWidth) * 100 : 50,
      clickY: window.innerHeight > 0 ? (y / window.innerHeight) * 100 : 50,
    };
  } catch (error) {
    return { error: 'Click index failed: ' + String(error) };
  }
})()"#;

const WAIT_SCRIPT: &str = "(() => ({ url: location.href, title: document.title }))()";

#[tauri::command]
pub async fn browser_click(
    app: AppHandle,
    label: String,
    selector: String,
) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    let script = render_script(
        CLICK_SCRIPT,
        &[("__NEOSWARM_SELECTOR__", script_literal(&selector))],
    );
    eval_json(&webview, script).await
}

#[tauri::command]
pub async fn browser_type(
    app: AppHandle,
    label: String,
    selector: String,
    text: String,
) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    let script = render_script(
        TYPE_SCRIPT,
        &[
            ("__NEOSWARM_SELECTOR__", script_literal(&selector)),
            ("__NEOSWARM_TEXT__", script_literal(&text)),
        ],
    );
    eval_json(&webview, script).await
}

#[tauri::command]
pub async fn browser_scroll(
    app: AppHandle,
    label: String,
    direction: String,
    amount: f64,
) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    let amount = if amount.is_finite() && amount > 0.0 {
        amount
    } else {
        500.0
    };
    let script = render_script(
        SCROLL_SCRIPT,
        &[
            ("__NEOSWARM_DIRECTION__", script_literal(&direction)),
            ("__NEOSWARM_AMOUNT__", number_literal(amount, 500.0)),
        ],
    );
    eval_json(&webview, script).await
}

#[tauri::command]
pub async fn browser_press_key(
    app: AppHandle,
    label: String,
    key: String,
) -> Result<Value, String> {
    if key.trim().is_empty() {
        return Ok(json!({ "error": "key parameter is required" }));
    }
    let webview = get_webview(&app, &label)?;
    let script = render_script(
        PRESS_KEY_SCRIPT,
        &[("__NEOSWARM_KEY__", script_literal(&key))],
    );
    eval_json(&webview, script).await
}

/// Capture the browser webview's visual surface natively.
///
/// On macOS this shells out to `/usr/sbin/screencapture` and returns a
/// base64-encoded PNG. Other platforms have no capture API on the Tauri
/// webview, so they return a JSON `{ "error": ... }` object.
#[tauri::command]
pub async fn browser_screenshot(app: AppHandle, label: String) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    let url = webview.url().map(|url| url.to_string()).unwrap_or_default();

    #[cfg(target_os = "macos")]
    {
        match capture_macos_screenshot(&webview) {
            Ok(image) => Ok(json!({ "image": image, "url": url })),
            Err(error) => Ok(json!({ "error": error, "url": url })),
        }
    }

    #[cfg(not(target_os = "macos"))]
    {
        let _ = url;
        Ok(json!({
            "error": "Native screenshot capture for Tauri child webviews is not available on this platform yet."
        }))
    }
}

#[cfg(target_os = "macos")]
fn capture_macos_screenshot(webview: &tauri::Webview<tauri::Wry>) -> Result<String, String> {
    let position = webview
        .position()
        .map_err(|error| format!("Could not read webview position: {error}"))?;
    let size = webview
        .size()
        .map_err(|error| format!("Could not read webview size: {error}"))?;
    let window = webview.window();
    let window_position = window
        .inner_position()
        .map_err(|error| format!("Could not read window position: {error}"))?;
    let scale = window
        .scale_factor()
        .map_err(|error| format!("Could not read window scale factor: {error}"))?;
    let scale = if scale.is_finite() && scale > 0.0 { scale } else { 1.0 };

    let x = ((window_position.x + position.x) as f64 / scale).round() as i64;
    let y = ((window_position.y + position.y) as f64 / scale).round() as i64;
    let width = (size.width as f64 / scale).round().max(1.0) as i64;
    let height = (size.height as f64 / scale).round().max(1.0) as i64;

    let path = std::env::temp_dir().join(format!(
        "neoswarm-screenshot-{}-{}.png",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_millis())
            .unwrap_or(0)
    ));

    let output = std::process::Command::new("/usr/sbin/screencapture")
        .arg("-x")
        .arg(format!("-R{x},{y},{width},{height}"))
        .arg("-t")
        .arg("png")
        .arg(&path)
        .output()
        .map_err(|error| format!("Failed to launch native screenshot: {error}"))?;

    if !output.status.success() {
        let _ = std::fs::remove_file(&path);
        return Err(format!(
            "Native screenshot failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }

    let bytes = std::fs::read(&path)
        .map_err(|error| format!("Could not read captured screenshot: {error}"))?;
    let _ = std::fs::remove_file(&path);
    Ok(base64_encode(&bytes))
}

#[cfg(target_os = "macos")]
fn base64_encode(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut encoded = String::with_capacity((bytes.len() + 2) / 3 * 4);
    for chunk in bytes.chunks(3) {
        let first = chunk[0] as u32;
        let second = chunk.get(1).copied().unwrap_or(0) as u32;
        let third = chunk.get(2).copied().unwrap_or(0) as u32;
        let packed = (first << 16) | (second << 8) | third;
        encoded.push(TABLE[((packed >> 18) & 63) as usize] as char);
        encoded.push(TABLE[((packed >> 12) & 63) as usize] as char);
        if chunk.len() > 1 {
            encoded.push(TABLE[((packed >> 6) & 63) as usize] as char);
        } else {
            encoded.push('=');
        }
        if chunk.len() > 2 {
            encoded.push(TABLE[(packed & 63) as usize] as char);
        } else {
            encoded.push('=');
        }
    }
    encoded
}

#[tauri::command]
pub async fn browser_get_text(
    app: AppHandle,
    label: String,
    selector: String,
) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    let script = render_script(
        GET_TEXT_SCRIPT,
        &[("__NEOSWARM_SELECTOR__", script_literal(&selector))],
    );
    eval_json(&webview, script).await
}

#[tauri::command]
pub async fn browser_get_elements(app: AppHandle, label: String) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    eval_json(&webview, GET_ELEMENTS_SCRIPT.to_string()).await
}

#[tauri::command]
pub async fn browser_list_interactives(app: AppHandle, label: String) -> Result<Value, String> {
    let webview = get_webview(&app, &label)?;
    eval_json(&webview, LIST_INTERACTIVES_SCRIPT.to_string()).await
}

#[tauri::command]
pub async fn browser_click_index(
    app: AppHandle,
    label: String,
    selector: String,
    index: i64,
) -> Result<Value, String> {
    if index < 1 {
        return Ok(json!({ "error": "index parameter is required and must be a positive integer" }));
    }
    let webview = get_webview(&app, &label)?;
    let script = render_script(
        CLICK_INDEX_SCRIPT,
        &[
            ("__NEOSWARM_SELECTOR__", script_literal(&selector)),
            ("__NEOSWARM_INDEX__", index.to_string()),
        ],
    );
    eval_json(&webview, script).await
}

#[tauri::command]
pub async fn browser_wait(
    app: AppHandle,
    label: String,
    milliseconds: f64,
) -> Result<Value, String> {
    let millis = if milliseconds.is_finite() && milliseconds > 0.0 {
        milliseconds.min(30000.0).round().max(1.0) as u64
    } else {
        500
    };
    let webview = get_webview(&app, &label)?;

    let _ = tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(millis));
    })
    .await;

    let info = eval_json(&webview, WAIT_SCRIPT.to_string())
        .await
        .unwrap_or(Value::Null);
    let url = info
        .get("url")
        .cloned()
        .unwrap_or_else(|| Value::String(String::new()));
    let title = info
        .get("title")
        .cloned()
        .unwrap_or_else(|| Value::String(String::new()));
    Ok(json!({
        "text": format!("Waited {millis}ms."),
        "url": url,
        "title": title,
    }))
}
