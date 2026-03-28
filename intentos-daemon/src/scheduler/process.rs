/// Represents a running agent process
pub struct AgentProcess {
    pub agent_name: String,
    pub pid: Option<u32>,
    pub status: ProcessStatus,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ProcessStatus {
    Starting,
    Running,
    Completed,
    Failed(String),
    TimedOut,
}

impl AgentProcess {
    pub fn new(agent_name: &str) -> Self {
        Self {
            agent_name: agent_name.to_string(),
            pid: None,
            status: ProcessStatus::Starting,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_creation() {
        let proc = AgentProcess::new("file_agent");
        assert_eq!(proc.agent_name, "file_agent");
        assert_eq!(proc.status, ProcessStatus::Starting);
        assert!(proc.pid.is_none());
    }
}
