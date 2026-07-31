use log::{error, info, warn};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Manager};

/// Managed backend child. Keeping the process in Tauri state lets the app
/// terminate it reliably instead of leaving an orphaned Uvicorn process.
pub struct BackendProcess(Mutex<Option<Child>>);

impl BackendProcess {
    fn new(child: Child) -> Self {
        Self(Mutex::new(Some(child)))
    }

    fn stop(&self) {
        let Ok(mut guard) = self.0.lock() else {
            return;
        };
        let Some(mut child) = guard.take() else {
            return;
        };
        if let Err(err) = child.kill() {
            warn!("Failed to stop backend process: {}", err);
        }
        let _ = child.wait();
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

pub fn spawn_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let resource_dir = app.path().resource_dir().ok();

    // Release bundles prefer the PyInstaller executable prepared by
    // scripts/build-backend-binary.sh. It contains Python and all backend
    // dependencies, so end users do not need a venv or system packages.
    if let Some(binary) = find_bundled_backend(resource_dir.as_deref()) {
        info!("Starting bundled backend executable: {:?}", binary);
        let child = Command::new(binary)
            .args(["--host", "127.0.0.1", "--port", "8324"])
            .env("NEOSWARM_PACKAGED", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()?;
        app.manage(BackendProcess::new(child));
        return Ok(());
    }

    // Development fallback: locate backend source and run it with the local
    // venv. This is intentionally a fallback; packaged builds should contain
    // the executable above.
    let backend_dir = find_backend_source(app)?;
    let project_root = backend_dir
        .parent()
        .ok_or("Backend directory has no project root")?;
    let venv_python = backend_dir.join(if cfg!(windows) {
        ".venv\\Scripts\\python.exe"
    } else {
        ".venv/bin/python"
    });
    let python = if venv_python.exists() {
        venv_python
    } else {
        PathBuf::from(if cfg!(windows) { "python" } else { "python3" })
    };

    info!("Starting development backend with {:?}", python);
    let child = Command::new(python)
        .args([
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8324",
        ])
        .current_dir(project_root)
        .env("PYTHONPATH", project_root)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|err| {
            error!("Failed to spawn backend: {}", err);
            err
        })?;

    app.manage(BackendProcess::new(child));
    Ok(())
}

pub fn shutdown_backend(app: &AppHandle) {
    if let Some(process) = app.try_state::<BackendProcess>() {
        process.stop();
    }
}

fn find_bundled_backend(resource_dir: Option<&Path>) -> Option<PathBuf> {
    let file_name = if cfg!(windows) {
        "neoswarm-backend.exe"
    } else {
        "neoswarm-backend"
    };
    let resource_dir = resource_dir?;
    let candidates = [
        resource_dir.join("backend-dist").join(file_name),
        resource_dir.join(file_name),
    ];
    candidates.into_iter().find(|path| path.is_file())
}

fn find_backend_source(app: &AppHandle) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let mut candidates = Vec::new();
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("backend"));
    }
    if let Ok(executable) = std::env::current_exe() {
        if let Some(directory) = executable.parent() {
            candidates.push(directory.join("backend"));
            if let Some(parent) = directory.parent() {
                candidates.push(parent.join("backend"));
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("backend"));
        candidates.push(cwd.join("..").join("backend"));
    }

    candidates
        .into_iter()
        .find(|path| path.join("main.py").is_file())
        .ok_or_else(|| {
            "No bundled backend executable or development backend source was found".into()
        })
}
