use log::{error, info};
use std::path::PathBuf;
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;

pub fn spawn_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    // Check multiple possible backend locations
    let exe_dir = std::env::current_exe()?.parent().map(|p| p.to_path_buf());
    
    let possible_paths = vec![
        // Bundled in Tauri resources
        app.path().resource_dir()?.join("backend"),
        // Development path
        PathBuf::from("/home/raijinnn0101/Development/NeoSwarm/backend"),
        // Next to the binary
        exe_dir.unwrap_or_default().join("backend"),
    ];

    let backend_dir = possible_paths
        .into_iter()
        .find(|p| p.exists() && p.join("main.py").exists());

    let backend_dir = match backend_dir {
        Some(d) => d,
        None => {
            // Just use dev path for now
            let dev_path = PathBuf::from("/home/raijinnn0101/Development/NeoSwarm/backend");
            if dev_path.exists() {
                dev_path
            } else {
                error!("No backend found");
                return Ok(());
            }
        }
    };

    info!("Found backend at: {:?}", backend_dir);

    // Find python
    let python = backend_dir.join(".venv/bin/python");
    let python_cmd = if python.exists() {
        python.to_string_lossy().to_string()
    } else {
        "python3".to_string()
    };

    let parent = backend_dir.parent().unwrap().to_string_lossy().to_string();
    
    info!("Starting backend with: {} {}", python_cmd, backend_dir.display());

    // Use bash -c for the full command
    let child = app
        .shell()
        .command("bash")
        .args([
            "-c",
            &format!(
                "cd '{}' && PYTHONPATH='{}' '{}' -m uvicorn backend.main:app --host 127.0.0.1 --port 8324",
                backend_dir.display(),
                parent,
                python_cmd
            ),
        ])
        .spawn()?;

    app.manage(child);
    info!("Backend spawned");
    Ok(())
}