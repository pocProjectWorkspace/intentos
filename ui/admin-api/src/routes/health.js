const { Router } = require('express');

const router = Router();
const startTime = Date.now();

router.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    version: '0.1.0',
    uptime_seconds: Math.floor((Date.now() - startTime) / 1000),
  });
});

module.exports = router;
