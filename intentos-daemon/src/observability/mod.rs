use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Audit log entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub timestamp: DateTime<Utc>,
    pub task_id: String,
    pub agent: String,
    pub action: String,
    pub paths_accessed: Vec<String>,
    pub result: String,
    pub duration_ms: u64,
    pub initiated_by: String,
}

/// Append-only audit logger
pub struct AuditLogger {
    entries: Vec<AuditEntry>,
}

impl AuditLogger {
    pub fn new() -> Self {
        Self { entries: Vec::new() }
    }

    pub fn log(&mut self, entry: AuditEntry) {
        self.entries.push(entry);
    }

    pub fn entries(&self) -> &[AuditEntry] {
        &self.entries
    }

    pub fn count(&self) -> usize {
        self.entries.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    #[test]
    fn test_audit_logging() {
        let mut logger = AuditLogger::new();
        logger.log(AuditEntry {
            timestamp: Utc::now(),
            task_id: "test-001".to_string(),
            agent: "file_agent".to_string(),
            action: "list_files".to_string(),
            paths_accessed: vec!["/tmp".to_string()],
            result: "success".to_string(),
            duration_ms: 50,
            initiated_by: "john".to_string(),
        });
        assert_eq!(logger.count(), 1);
        assert_eq!(logger.entries()[0].agent, "file_agent");
    }
}
