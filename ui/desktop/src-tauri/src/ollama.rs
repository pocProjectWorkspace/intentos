//! Ollama lifecycle management for the desktop app.
//!
//! Detects, installs, starts the daemon, and pulls models with
//! progress events streamed to the frontend.

use serde::{Deserialize, Serialize};
use std::process::Command;
use tauri::Emitter;

const OLLAMA_API: &str = "http://localhost:11434";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OllamaStatus {
    pub installed: bool,
    pub running: bool,
    pub version: String,
    pub models: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PullProgress {
    pub model: String,
    pub status: String,
    pub percent: f64,
}

/// Check the current state of Ollama.
pub async fn check_status() -> OllamaStatus {
    let installed = is_installed();
    let running = is_running().await;
    let version = if installed { get_version() } else { String::new() };
    let models = if running { list_models().await } else { vec![] };

    OllamaStatus { installed, running, version, models }
}

/// Check if the ollama binary is on PATH.
pub fn is_installed() -> bool {
    which::which("ollama").is_ok()
        || Command::new("ollama")
            .arg("--version")
            .output()
            .is_ok()
}

/// Get Ollama version string.
pub fn get_version() -> String {
    Command::new("ollama")
        .arg("--version")
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| {
            s.trim()
                .strip_prefix("ollama version ")
                .unwrap_or(s.trim())
                .to_string()
        })
        .unwrap_or_default()
}

/// Check if the Ollama daemon is responding.
pub async fn is_running() -> bool {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .build();

    match client {
        Ok(c) => c
            .get(format!("{OLLAMA_API}/api/tags"))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false),
        Err(_) => false,
    }
}

/// List locally available models.
pub async fn list_models() -> Vec<String> {
    let client = match reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(_) => return vec![],
    };

    let resp = match client.get(format!("{OLLAMA_API}/api/tags")).send().await {
        Ok(r) => r,
        Err(_) => return vec![],
    };

    let body: serde_json::Value = match resp.json().await {
        Ok(v) => v,
        Err(_) => return vec![],
    };

    body["models"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|m| m["name"].as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default()
}

/// Start the Ollama daemon in the background.
pub async fn start_daemon() -> Result<(), String> {
    if is_running().await {
        return Ok(());
    }

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        Command::new("ollama")
            .arg("serve")
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("Failed to start Ollama: {e}"))?;
    }

    #[cfg(not(target_os = "windows"))]
    {
        Command::new("ollama")
            .arg("serve")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .map_err(|e| format!("Failed to start Ollama: {e}"))?;
    }

    // Wait for it to be ready
    for _ in 0..20 {
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        if is_running().await {
            return Ok(());
        }
    }

    Err("Ollama started but did not respond within 10 seconds".to_string())
}

/// Install Ollama for the current platform.
pub async fn install() -> Result<(), String> {
    if is_installed() {
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        // Try brew first, then curl installer
        let brew_result = Command::new("brew")
            .args(["install", "ollama", "--quiet"])
            .output();

        if brew_result.map(|o| o.status.success()).unwrap_or(false) {
            return Ok(());
        }

        let curl_result = Command::new("bash")
            .args(["-c", "curl -fsSL https://ollama.com/install.sh | sh"])
            .output()
            .map_err(|e| format!("Install failed: {e}"))?;

        if curl_result.status.success() {
            Ok(())
        } else {
            Err("Could not install the local AI engine. Visit https://ollama.com/download".to_string())
        }
    }

    #[cfg(target_os = "windows")]
    {
        // Try winget first
        let winget_result = Command::new("winget")
            .args([
                "install", "Ollama.Ollama",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent",
            ])
            .output();

        if winget_result.map(|o| o.status.success()).unwrap_or(false) {
            return Ok(());
        }

        Err("Could not install the local AI engine. Visit https://ollama.com/download".to_string())
    }

    #[cfg(target_os = "linux")]
    {
        let result = Command::new("bash")
            .args(["-c", "curl -fsSL https://ollama.com/install.sh | sh"])
            .output()
            .map_err(|e| format!("Install failed: {e}"))?;

        if result.status.success() {
            Ok(())
        } else {
            Err("Could not install the local AI engine. Visit https://ollama.com/download".to_string())
        }
    }
}

/// Pull a model via the Ollama API.
pub async fn pull_model(
    model_name: &str,
    app: &tauri::AppHandle,
) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(1800))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    let resp = client
        .post(format!("{OLLAMA_API}/api/pull"))
        .json(&serde_json::json!({"name": model_name, "stream": true}))
        .send()
        .await
        .map_err(|e| format!("Pull request failed: {e}"))?;

    let mut stream = resp.bytes_stream();
    use futures_util::StreamExt;

    let mut buffer = Vec::new();
    while let Some(chunk) = stream.next().await {
        let bytes = chunk.map_err(|e| format!("Stream error: {e}"))?;
        buffer.extend_from_slice(&bytes);

        // Process complete JSON lines
        while let Some(pos) = buffer.iter().position(|&b| b == b'\n') {
            let line: Vec<u8> = buffer.drain(..=pos).collect();
            let line_str = String::from_utf8_lossy(&line);

            if let Ok(data) = serde_json::from_str::<serde_json::Value>(line_str.trim()) {
                if let Some(err) = data["error"].as_str() {
                    return Err(format!("Pull failed: {err}"));
                }

                let status_raw = data["status"].as_str().unwrap_or("");
                let completed = data["completed"].as_u64().unwrap_or(0);
                let total = data["total"].as_u64().unwrap_or(0);

                let status = if status_raw.contains("pulling") || status_raw.contains("downloading") {
                    "downloading"
                } else if status_raw.contains("verifying") {
                    "verifying"
                } else if status_raw == "success" {
                    "complete"
                } else {
                    status_raw
                };

                let percent = if total > 0 {
                    (completed as f64 / total as f64) * 100.0
                } else if status == "complete" {
                    100.0
                } else {
                    0.0
                };

                let progress = PullProgress {
                    model: model_name.to_string(),
                    status: status.to_string(),
                    percent,
                };

                let _ = app.emit("ollama://pull-progress", &progress);
            }
        }
    }

    Ok(())
}
