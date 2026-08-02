mod browser;
mod sidecar;

pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    log::info!("Starting NeoSwarm app...");

    let app = tauri::Builder::default()
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
