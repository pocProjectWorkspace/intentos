use clap::Parser;
use tracing::info;

mod scheduler;
mod sandbox;
mod security;
mod proxy;
mod ipc;
mod observability;

#[derive(Parser)]
#[command(name = "intentos-daemon", about = "IntentOS Agent Execution Daemon")]
struct Cli {
    /// Port to listen on
    #[arg(short, long, default_value = "7890")]
    port: u16,

    /// Config file path
    #[arg(short = 'f', long, default_value = "~/.intentos/daemon.toml")]
    config: String,

    /// Log level
    #[arg(short, long, default_value = "info")]
    log_level: String,
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();

    tracing_subscriber::fmt()
        .with_env_filter(&cli.log_level)
        .init();

    info!("IntentOS Daemon v{} starting on port {}", env!("CARGO_PKG_VERSION"), cli.port);
    info!("Security boundary active — all agents execute through this process");

    // TODO: Initialize subsystems
    // 1. Load config
    // 2. Initialize credential store
    // 3. Start scheduler
    // 4. Start IPC listener for Python agents
    // 5. Start health check endpoint

    info!("Daemon ready");

    // Keep running
    tokio::signal::ctrl_c().await.expect("Failed to listen for ctrl+c");
    info!("Shutting down");
}
