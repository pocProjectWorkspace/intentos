/// IPC bridge between Rust daemon and Python agents
/// Uses JSON over stdin/stdout

use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct AgentRequest {
    pub action: String,
    pub params: serde_json::Value,
    pub context: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AgentResponse {
    pub status: String,
    pub action_performed: String,
    pub result: serde_json::Value,
    pub metadata: serde_json::Value,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_request_serialization() {
        let req = AgentRequest {
            action: "list_files".to_string(),
            params: serde_json::json!({"path": "/tmp"}),
            context: serde_json::json!({"dry_run": false}),
        };
        let json = serde_json::to_string(&req).unwrap();
        let parsed: AgentRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.action, "list_files");
    }
}
