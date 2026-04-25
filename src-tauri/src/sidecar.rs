use log::{error, info};
use std::path::PathBuf;
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;

pub fn spawn_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    // Get executable directory
    let exe_dir = std::env::current_exe()?.parent().map(|p| p.to_path_buf());
    
    // Get the app data/resource directory
    let resource_dir = app.path().resource_dir().ok();
    
    info!("Searching for backend...");
    info!("Executable dir: {:?}", exe_dir);
    info!("Resource dir: {:?}", resource_dir);
    
    // Build list of possible backend locations
    let mut possible_paths: Vec<PathBuf> = vec![];
    
    // 1. Resource directory (for AppImage bundles)
    if let Some(ref res_dir) = resource_dir {
        let backend_in_resource = res_dir.join("backend");
        if backend_in_resource.exists() {
            info!("Found backend in resource dir: {:?}", backend_in_resource);
            possible_paths.push(backend_in_resource);
        }
    }
    
    // 2. Next to the binary (for standalone binary)
    if let Some(ref dir) = exe_dir {
        let next_to_binary = dir.join("backend");
        if next_to_binary.exists() {
            info!("Found backend next to binary: {:?}", next_to_binary);
            possible_paths.push(next_to_binary);
        }
        
        // Also try parent directory (in case binary is in subfolder)
        if let Some(ref parent) = dir.parent() {
            let parent_backend = parent.join("backend");
            if parent_backend.exists() {
                info!("Found backend in parent of binary: {:?}", parent_backend);
                possible_paths.push(parent_backend);
            }
        }
    }
    
    // 3. Development path (absolute path for development)
    let dev_path = PathBuf::from("/home/raijinnn0101/Development/NeoSwarm/backend");
    if dev_path.exists() {
        info!("Found development backend: {:?}", dev_path);
        possible_paths.push(dev_path);
    }
    
    // 4. Current working directory
    if let Ok(cwd) = std::env::current_dir() {
        let cwd_backend = cwd.join("backend");
        if cwd_backend.exists() {
            info!("Found backend in CWD: {:?}", cwd_backend);
            possible_paths.push(cwd_backend);
        }
    }
    
    // Find the first valid backend directory
    let backend_dir = possible_paths
        .into_iter()
        .find(|p| p.exists() && p.join("main.py").exists());

    let backend_dir = match backend_dir {
        Some(d) => d,
        None => {
            // Last fallback: try release build directory if it exists
            let release_backend = PathBuf::from("/home/raijinnn0101/Development/NeoSwarm/src-tauri/target/release/backend");
            if release_backend.exists() {
                info!("Found backend in release folder: {:?}", release_backend);
                release_backend
            } else {
                error!("No backend found in any location");
                return Ok(());
            }
        }
    };

    info!("Using backend at: {:?}", backend_dir);

    // Find python - prefer venv
    let venv_python = backend_dir.join(".venv/bin/python");
    let python_cmd = if venv_python.exists() {
        venv_python.to_string_lossy().to_string()
    } else {
        // Try system python
        "python3".to_string()
    };

    let parent = backend_dir.parent().unwrap().to_string_lossy().to_string();
    
    info!("Starting backend with python: {}", python_cmd);

    // Build the startup command
    let startup_cmd = format!(
        "cd '{}' && PYTHONPATH='{}' '{}' -m uvicorn backend.main:app --host 127.0.0.1 --port 8324",
        backend_dir.display(),
        parent,
        python_cmd
    );
    
    info!("Startup command: {}", startup_cmd);

    // Use bash -c to run the command
    let child = app
        .shell()
        .command("bash")
        .args(["-c", &startup_cmd])
        .spawn()
        .map_err(|e| {
            error!("Failed to spawn backend: {}", e);
            Box::new(e) as Box<dyn std::error::Error>
        })?;

    app.manage(child);
    info!("Backend spawned successfully");
    Ok(())
}
