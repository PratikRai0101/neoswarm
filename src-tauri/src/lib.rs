mod browser;
mod sidecar;

use std::path::PathBuf;

use tauri::Manager;
use tauri_plugin_opener::OpenerExt;

fn artifact_data_roots(app: &tauri::AppHandle) -> Vec<PathBuf> {
    if let Ok(override_root) = std::env::var("NEOSWARM_DATA_DIR") {
        return vec![PathBuf::from(override_root)];
    }

    let mut roots = Vec::new();
    // The backend child receives NEOSWARM_PACKAGED, but the Tauri parent does
    // not. Always include the platform data location so this remains valid
    // for a DMG-launched app as well as a development launch.
    if let Ok(home) = app.path().home_dir() {
        #[cfg(target_os = "macos")]
        roots.push(home.join("Library/Application Support/NeoSwarm/data"));
        #[cfg(target_os = "windows")]
        roots.push(
            std::env::var_os("APPDATA")
                .map(PathBuf::from)
                .unwrap_or_else(|| home.join("AppData/Roaming"))
                .join("NeoSwarm/data"),
        );
        #[cfg(all(unix, not(target_os = "macos")))]
        roots.push(
            std::env::var_os("XDG_DATA_HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| home.join(".local/share"))
                .join("NeoSwarm/data"),
        );
    }
    if std::env::var("NEOSWARM_PACKAGED").as_deref() != Ok("1") {
        if let Ok(cwd) = std::env::current_dir() {
            roots.push(cwd.join("backend/data"));
            if let Some(parent) = cwd.parent() {
                roots.push(parent.join("backend/data"));
            }
        }
    }
    roots
}

#[tauri::command]
fn open_artifact(app: tauri::AppHandle, artifact_id: String) -> Result<(), String> {
    if artifact_id.len() != 32
        || !artifact_id
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return Err("Invalid artifact ID".to_string());
    }

    for data_root in artifact_data_roots(&app) {
        let artifact_dir = data_root.join("artifacts");
        let content = artifact_dir.join(format!("{artifact_id}.bin"));
        let metadata = artifact_dir.join(format!("{artifact_id}.json"));
        if !content.is_file() || !metadata.is_file() {
            continue;
        }

        let canonical_dir = std::fs::canonicalize(&artifact_dir)
            .map_err(|error| format!("Could not access artifact directory: {error}"))?;
        let canonical_content = std::fs::canonicalize(&content)
            .map_err(|error| format!("Could not access artifact: {error}"))?;
        if canonical_content.parent() != Some(canonical_dir.as_path()) {
            return Err("Artifact path is outside the artifact workspace".to_string());
        }

        return app
            .opener()
            .open_path(canonical_content.to_string_lossy(), None::<String>)
            .map_err(|error| format!("Could not open artifact: {error}"));
    }

    Err("Artifact not found".to_string())
}

pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    log::info!("Starting NeoSwarm app...");

    let app = tauri::Builder::default()
        // Must be registered first so repeated launches hand off to the
        // existing process instead of starting another backend.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![
            browser::browser_eval,
            browser::browser_navigate,
            browser::browser_reload,
            browser::browser_history,
            browser::browser_url,
            open_artifact,
        ])
        .setup(|app| {
            #[cfg(desktop)]
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;
            log::info!("Setting up backend...");
            #[cfg(desktop)]
            {
                if let Err(error) = sidecar::spawn_backend(app.handle()) {
                    log::error!("Backend spawn error: {}", error);
                } else {
                    log::info!("Backend process started");
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!());

    match app {
        Ok(app) => app.run(|app_handle, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                #[cfg(desktop)]
                sidecar::shutdown_backend(app_handle);
                log::info!("NeoSwarm exited normally");
            }
        }),
        Err(error) => log::error!("Error running NeoSwarm: {}", error),
    }
}
