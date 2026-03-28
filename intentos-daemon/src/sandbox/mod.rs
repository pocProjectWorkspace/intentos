pub mod policy;

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Three-tier sandbox policy
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SandboxPolicy {
    ReadOnly,
    WorkspaceWrite,
    FullAccess,
}

/// File operation types
#[derive(Debug, Clone, PartialEq)]
pub enum FileOp {
    Read,
    Write,
    Delete,
    CreateDir,
    Move,
    Copy,
    Execute,
}

/// Result of a sandbox check
#[derive(Debug)]
pub struct CheckResult {
    pub allowed: bool,
    pub reason: String,
}

/// Sandbox for an agent execution
pub struct Sandbox {
    policy: SandboxPolicy,
    granted_paths: Vec<PathBuf>,
    workspace: PathBuf,
    denied_paths: Vec<PathBuf>,
}

impl Sandbox {
    pub fn new(
        policy: SandboxPolicy,
        granted_paths: Vec<PathBuf>,
        workspace: PathBuf,
        denied_paths: Vec<PathBuf>,
    ) -> Self {
        Self {
            policy,
            granted_paths,
            workspace,
            denied_paths,
        }
    }

    /// Check if an operation is allowed on a path
    pub fn check(&self, op: &FileOp, path: &PathBuf) -> CheckResult {
        // Check denied paths first
        let resolved = path.canonicalize().unwrap_or_else(|_| path.clone());

        for denied in &self.denied_paths {
            if resolved.starts_with(denied) {
                return CheckResult {
                    allowed: false,
                    reason: format!("Path is in denied list: {}", denied.display()),
                };
            }
        }

        // Check policy
        match self.policy {
            SandboxPolicy::ReadOnly => {
                if matches!(op, FileOp::Read) {
                    self.check_granted(&resolved)
                } else {
                    CheckResult {
                        allowed: false,
                        reason: "ReadOnly policy: only read operations allowed".to_string(),
                    }
                }
            }
            SandboxPolicy::WorkspaceWrite => {
                match op {
                    FileOp::Read => self.check_granted(&resolved),
                    FileOp::Write | FileOp::CreateDir | FileOp::Delete => {
                        if resolved.starts_with(&self.workspace) {
                            CheckResult { allowed: true, reason: "Within workspace".to_string() }
                        } else {
                            CheckResult {
                                allowed: false,
                                reason: "WorkspaceWrite: writes only allowed in workspace".to_string(),
                            }
                        }
                    }
                    _ => self.check_granted(&resolved),
                }
            }
            SandboxPolicy::FullAccess => self.check_granted(&resolved),
        }
    }

    fn check_granted(&self, resolved: &PathBuf) -> CheckResult {
        for granted in &self.granted_paths {
            if resolved.starts_with(granted) {
                return CheckResult { allowed: true, reason: "Path is granted".to_string() };
            }
        }
        if resolved.starts_with(&self.workspace) {
            return CheckResult { allowed: true, reason: "Within workspace".to_string() };
        }
        CheckResult {
            allowed: false,
            reason: "Path is not in granted paths".to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_readonly_allows_read() {
        let sandbox = Sandbox::new(
            SandboxPolicy::ReadOnly,
            vec![PathBuf::from("/tmp/test")],
            PathBuf::from("/tmp/workspace"),
            vec![],
        );
        let result = sandbox.check(&FileOp::Read, &PathBuf::from("/tmp/test/file.txt"));
        assert!(result.allowed);
    }

    #[test]
    fn test_readonly_blocks_write() {
        let sandbox = Sandbox::new(
            SandboxPolicy::ReadOnly,
            vec![PathBuf::from("/tmp/test")],
            PathBuf::from("/tmp/workspace"),
            vec![],
        );
        let result = sandbox.check(&FileOp::Write, &PathBuf::from("/tmp/test/file.txt"));
        assert!(!result.allowed);
    }

    #[test]
    fn test_denied_path_always_blocked() {
        let sandbox = Sandbox::new(
            SandboxPolicy::FullAccess,
            vec![PathBuf::from("/tmp")],
            PathBuf::from("/tmp/workspace"),
            vec![PathBuf::from("/tmp/secret")],
        );
        let result = sandbox.check(&FileOp::Read, &PathBuf::from("/tmp/secret/key.pem"));
        assert!(!result.allowed);
    }
}
