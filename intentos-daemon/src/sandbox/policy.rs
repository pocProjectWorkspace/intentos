use serde::{Deserialize, Serialize};

/// Sandbox resource limits
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceLimits {
    pub max_memory_mb: u64,
    pub max_cpu_seconds: u64,
    pub max_output_bytes: u64,
}

impl Default for ResourceLimits {
    fn default() -> Self {
        Self {
            max_memory_mb: 2048,
            max_cpu_seconds: 120,
            max_output_bytes: 65536,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_limits() {
        let limits = ResourceLimits::default();
        assert_eq!(limits.max_memory_mb, 2048);
        assert_eq!(limits.max_cpu_seconds, 120);
        assert_eq!(limits.max_output_bytes, 65536);
    }
}
