/// Network proxy with domain allowlisting
/// Credentials injected at proxy boundary, never in agent code

pub struct NetworkProxy {
    allowed_domains: Vec<String>,
}

impl NetworkProxy {
    pub fn new() -> Self {
        Self {
            allowed_domains: vec![
                "github.com".to_string(),
                "api.anthropic.com".to_string(),
                "api.openai.com".to_string(),
                "registry.npmjs.org".to_string(),
                "pypi.org".to_string(),
            ],
        }
    }

    pub fn is_allowed(&self, domain: &str) -> bool {
        self.allowed_domains.iter().any(|d| d == domain)
    }

    pub fn add_domain(&mut self, domain: String) {
        if !self.allowed_domains.contains(&domain) {
            self.allowed_domains.push(domain);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_allowlist() {
        let proxy = NetworkProxy::new();
        assert!(proxy.is_allowed("github.com"));
        assert!(proxy.is_allowed("api.anthropic.com"));
        assert!(!proxy.is_allowed("evil.com"));
    }

    #[test]
    fn test_add_domain() {
        let mut proxy = NetworkProxy::new();
        assert!(!proxy.is_allowed("custom.api.com"));
        proxy.add_domain("custom.api.com".to_string());
        assert!(proxy.is_allowed("custom.api.com"));
    }
}
