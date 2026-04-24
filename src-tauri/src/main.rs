#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use log::info;

mod sidecar;

fn main() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            info!("NeoSwarm starting...");

            #[cfg(desktop)]
            {
                sidecar::spawn_backend(app.handle())?;
                info!("Backend sidecar started");
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running NeoSwarm");
}