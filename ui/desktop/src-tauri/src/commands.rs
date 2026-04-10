//! Tauri IPC command handlers.
//!
//! These are exposed to the React frontend via `invoke()`.

use crate::{ollama, sidecar};
use tauri::Emitter;
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct BackendStatus {
    pub backend_alive: bool,
    pub ollama: ollama::OllamaStatus,
}

#[derive(Debug, Serialize)]
pub struct PlatformInfo {
    pub os: String,
    pub arch: String,
    pub app_version: String,
}

#[tauri::command]
pub async fn get_backend_status() -> Result<BackendStatus, String> {
    let backend_alive = sidecar::is_backend_alive().await;
    let ollama_status = ollama::check_status().await;

    Ok(BackendStatus {
        backend_alive,
        ollama: ollama_status,
    })
}

#[tauri::command]
pub async fn restart_backend(app: tauri::AppHandle) -> Result<(), String> {
    sidecar::start_sidecar(&app).await
}

#[tauri::command]
pub async fn get_ollama_status() -> Result<ollama::OllamaStatus, String> {
    Ok(ollama::check_status().await)
}

#[tauri::command]
pub async fn setup_ollama(model_name: String, app: tauri::AppHandle) -> Result<(), String> {
    // Install if needed
    if !ollama::is_installed() {
        let _ = app.emit("ollama://status", "installing");
        ollama::install().await?;
    }

    // Start daemon if needed
    if !ollama::is_running().await {
        let _ = app.emit("ollama://status", "starting");
        ollama::start_daemon().await?;
    }

    // Pull the requested model
    let _ = app.emit("ollama://status", "pulling");
    ollama::pull_model(&model_name, &app).await?;

    // Pull embedding model
    let _ = app.emit("ollama://status", "pulling-embeddings");
    ollama::pull_model("nomic-embed-text", &app).await?;

    let _ = app.emit("ollama://status", "ready");
    Ok(())
}

#[tauri::command]
pub fn get_platform_info() -> PlatformInfo {
    PlatformInfo {
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        app_version: env!("CARGO_PKG_VERSION").to_string(),
    }
}

#[tauri::command]
pub fn open_logs_folder() -> Result<(), String> {
    let logs_dir = dirs::home_dir()
        .ok_or("Could not find home directory")?
        .join(".intentos")
        .join("logs");

    if logs_dir.exists() {
        open::that(&logs_dir).map_err(|e| format!("Could not open folder: {e}"))?;
    } else {
        return Err("Logs folder does not exist yet".to_string());
    }

    Ok(())
}
