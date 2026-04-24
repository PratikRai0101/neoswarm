mod sidecar;

pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            log::info!("NeoSwarm starting...");

            #[cfg(desktop)]
            {
                sidecar::spawn_backend(app.handle())?;
                log::info!("Backend sidecar started");
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running NeoSwarm");
}
