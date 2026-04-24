mod sidecar;

pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    log::info!("Starting NeoSwarm app...");

    let result = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            log::info!("Setting up backend...");
            #[cfg(desktop)]
            {
                if let Err(e) = sidecar::spawn_backend(app.handle()) {
                    log::error!("Backend spawn error: {}", e);
                } else {
                    log::info!("Backend spawn attempted");
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!());

    match result {
        Ok(_) => log::info!("NeoSwarm exited normally"),
        Err(e) => log::error!("Error running NeoSwarm: {}", e),
    }
}
