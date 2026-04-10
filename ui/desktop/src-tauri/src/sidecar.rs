//! Python sidecar lifecycle management.
//!
//! Spawns the PyInstaller-bundled IntentOS backend as a Tauri sidecar,
//! waits for the health endpoint, and handles shutdown.

use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 7891;
const HEALTH_URL: &str = "http://127.0.0.1:7891/api/health";
const MAX_HEALTH_RETRIES: u32 = 60;
const HEALTH_INTERVAL_MS: u64 = 500;

/// Start the Python backend sidecar and wait until it's ready.
pub async fn start_sidecar(app: &AppHandle) -> Result<(), String> {
    let shell = app.shell();

    let (mut _rx, _child) = shell
        .sidecar("intentos-backend")
        .map_err(|e| format!("Failed to create sidecar command: {e}"))?
        .args(["--headless", "--host", BACKEND_HOST, "--port", &BACKEND_PORT.to_string()])
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

    // Wait for health endpoint
    wait_for_ready().await?;

    Ok(())
}

/// Poll the health endpoint until the backend responds.
async fn wait_for_ready() -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    for i in 0..MAX_HEALTH_RETRIES {
        match client.get(HEALTH_URL).send().await {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            _ => {
                if i % 10 == 0 && i > 0 {
                    eprintln!("Waiting for backend... ({i}/{MAX_HEALTH_RETRIES})");
                }
                tokio::time::sleep(std::time::Duration::from_millis(HEALTH_INTERVAL_MS)).await;
            }
        }
    }

    Err("Backend did not start within 30 seconds".to_string())
}

/// Check if the backend is currently responding.
pub async fn is_backend_alive() -> bool {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build();

    match client {
        Ok(c) => c.get(HEALTH_URL).send().await.map(|r| r.status().is_success()).unwrap_or(false),
        Err(_) => false,
    }
}
