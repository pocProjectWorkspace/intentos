mod commands;
mod ollama;
mod sidecar;

use tauri::{Emitter, Manager};

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Bootstrap: Ollama check → sidecar start → ready
            tauri::async_runtime::spawn(async move {
                // 1. Check and start Ollama if available
                let ollama_status = ollama::check_status().await;
                let _ = handle.emit("backend://ollama-status", &ollama_status);

                if ollama_status.installed && !ollama_status.running {
                    let _ = ollama::start_daemon().await;
                }

                // 2. Start Python sidecar
                match sidecar::start_sidecar(&handle).await {
                    Ok(_) => {
                        let _ = handle.emit("backend://ready", true);
                    }
                    Err(e) => {
                        let _ = handle.emit("backend://error", e.to_string());
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_backend_status,
            commands::restart_backend,
            commands::get_ollama_status,
            commands::setup_ollama,
            commands::get_platform_info,
            commands::open_logs_folder,
        ])
        .run(tauri::generate_context!())
        .expect("error while running IntentOS");
}
