use serde_json::Value;
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
