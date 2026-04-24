use log::{error, info};
use std::path::PathBuf;
use std::process::Command;
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;

pub fn spawn_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let resource_dir = app.path().resource_dir()?;
    let backend_dir: PathBuf = resource_dir.join("backend");

    if !backend_dir.exists() {
        error!("Backend directory not found: {:?}", backend_dir);
        return Ok(());
    }

    info!("Spawning backend from: {:?}", backend_dir.display());

    let python = find_python();
    info!("Using Python: {}", python);

    let child = app
        .shell()
        .command(&python)
        .args([
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8324",
        ])
        .current_dir(backend_dir)
        .spawn()?;

    app.manage(child);
    info!("Backend process spawned");

    Ok(())
}

fn find_python() -> String {
    let candidates = [
        "python3",
        "python",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    ];

    for candidate in &candidates {
        if let Ok(output) = Command::new(candidate).arg("--version").output() {
            if output.status.success() {
                return candidate.to_string();
            }
        }
    }

    "python3".to_string()
}
