pub mod pool;
pub mod process;

use serde::{Deserialize, Serialize};

/// Agent manifest declaring capabilities and permissions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentManifest {
    pub name: String,
    pub version: String,
    pub actions: Vec<String>,
    pub permissions: Vec<String>,
    pub sandbox_policy: String,
}

/// Result of an agent execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionResult {
    pub agent_name: String,
    pub action: String,
    pub status: String,
    pub output: serde_json::Value,
    pub duration_ms: u64,
    pub error: Option<String>,
}

/// The agent scheduler — spawns, manages, and isolates agent execution
pub struct Scheduler {
    agents: std::collections::HashMap<String, AgentManifest>,
}

impl Scheduler {
    pub fn new() -> Self {
        Self {
            agents: std::collections::HashMap::new(),
        }
    }

    pub fn register(&mut self, manifest: AgentManifest) {
        self.agents.insert(manifest.name.clone(), manifest);
    }

    pub fn is_registered(&self, name: &str) -> bool {
        self.agents.contains_key(name)
    }

    pub fn list_agents(&self) -> Vec<String> {
        self.agents.keys().cloned().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_register_and_list() {
        let mut scheduler = Scheduler::new();
        let manifest = AgentManifest {
            name: "file_agent".to_string(),
            version: "0.1.0".to_string(),
            actions: vec!["list_files".to_string(), "read_file".to_string()],
            permissions: vec!["filesystem.read".to_string()],
            sandbox_policy: "WorkspaceWrite".to_string(),
        };
        scheduler.register(manifest);
        assert!(scheduler.is_registered("file_agent"));
        assert!(!scheduler.is_registered("unknown"));
        assert_eq!(scheduler.list_agents().len(), 1);
    }
}
