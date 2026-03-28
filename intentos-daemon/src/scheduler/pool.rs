/// Worker pool for concurrent agent execution
pub struct WorkerPool {
    max_workers: usize,
}

impl WorkerPool {
    pub fn new(max_workers: usize) -> Self {
        Self { max_workers }
    }

    pub fn max_workers(&self) -> usize {
        self.max_workers
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pool_creation() {
        let pool = WorkerPool::new(4);
        assert_eq!(pool.max_workers(), 4);
    }
}
