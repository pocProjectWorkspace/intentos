use regex::Regex;

pub struct LeakDetector {
    patterns: Vec<CredentialPattern>,
}

struct CredentialPattern {
    name: String,
    regex: Regex,
    severity: Severity,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Severity {
    Critical,
    High,
    Medium,
}

impl LeakDetector {
    pub fn new() -> Self {
        Self {
            patterns: vec![
                CredentialPattern {
                    name: "anthropic_api_key".to_string(),
                    regex: Regex::new(r"sk-ant-api\d{2}-[a-zA-Z0-9_-]{20,}").unwrap(),
                    severity: Severity::Critical,
                },
            ],
        }
    }

    pub fn scan(&self, text: &str) -> Vec<Detection> {
        let mut detections = Vec::new();
        for pattern in &self.patterns {
            for m in pattern.regex.find_iter(text) {
                detections.push(Detection {
                    pattern_name: pattern.name.clone(),
                    severity: pattern.severity.clone(),
                    start: m.start(),
                    end: m.end(),
                });
            }
        }
        detections
    }
}

#[derive(Debug)]
pub struct Detection {
    pub pattern_name: String,
    pub severity: Severity,
    pub start: usize,
    pub end: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detects_anthropic_key() {
        let detector = LeakDetector::new();
        let text = "My key is sk-ant-api03-abcdefghijklmnopqrstuvwx";
        let detections = detector.scan(text);
        assert_eq!(detections.len(), 1);
        assert_eq!(detections[0].pattern_name, "anthropic_api_key");
        assert_eq!(detections[0].severity, Severity::Critical);
    }

    #[test]
    fn test_clean_text() {
        let detector = LeakDetector::new();
        let detections = detector.scan("This is safe text with no secrets");
        assert!(detections.is_empty());
    }
}
