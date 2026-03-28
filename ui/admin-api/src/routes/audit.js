const { Router } = require('express');
const { fetchBridge } = require('../bridge-client');

const router = Router();

// In-memory store with seed data (fallback when bridge is unavailable)
const auditEvents = [
  { id: 1, timestamp: '2026-03-28T10:00:00Z', severity: 'info', agent: 'agent-alpha', action: 'login', details: 'User logged in' },
  { id: 2, timestamp: '2026-03-28T10:05:00Z', severity: 'warning', agent: 'agent-beta', action: 'policy_violation', details: 'Network access attempted' },
  { id: 3, timestamp: '2026-03-28T10:10:00Z', severity: 'error', agent: 'agent-alpha', action: 'sandbox_escape', details: 'Sandbox breach detected' },
  { id: 4, timestamp: '2026-03-28T10:15:00Z', severity: 'info', agent: 'agent-gamma', action: 'deployment', details: 'Model deployed successfully' },
  { id: 5, timestamp: '2026-03-28T10:20:00Z', severity: 'info', agent: 'agent-beta', action: 'login', details: 'User logged in' },
];

// List audit events with filters — tries Python bridge first
router.get('/api/audit', async (req, res) => {
  try {
    const realData = await fetchBridge('/bridge/audit');
    // Apply filters on bridge data
    let filtered = [...realData.events];
    const { limit, offset, severity, agent, since, until } = req.query;

    if (severity) {
      filtered = filtered.filter((e) => e.severity === severity);
    }
    if (agent) {
      filtered = filtered.filter((e) => e.agent === agent);
    }
    if (since) {
      filtered = filtered.filter((e) => e.timestamp >= since);
    }
    if (until) {
      filtered = filtered.filter((e) => e.timestamp <= until);
    }

    const total = filtered.length;
    const off = parseInt(offset, 10) || 0;
    const lim = parseInt(limit, 10) || 50;
    filtered = filtered.slice(off, off + lim);

    return res.json({ total, offset: off, limit: lim, events: filtered });
  } catch {
    // Bridge unavailable — use in-memory fallback
    let filtered = [...auditEvents];
    const { limit, offset, severity, agent, since, until } = req.query;

    if (severity) {
      filtered = filtered.filter((e) => e.severity === severity);
    }
    if (agent) {
      filtered = filtered.filter((e) => e.agent === agent);
    }
    if (since) {
      filtered = filtered.filter((e) => e.timestamp >= since);
    }
    if (until) {
      filtered = filtered.filter((e) => e.timestamp <= until);
    }

    const total = filtered.length;
    const off = parseInt(offset, 10) || 0;
    const lim = parseInt(limit, 10) || 50;
    filtered = filtered.slice(off, off + lim);

    res.json({ total, offset: off, limit: lim, events: filtered });
  }
});

// Export as JSON or CSV
router.get('/api/audit/export', (req, res) => {
  const format = req.query.format || 'json';

  if (format === 'csv') {
    const header = 'id,timestamp,severity,agent,action,details';
    const rows = auditEvents.map((e) =>
      `${e.id},${e.timestamp},${e.severity},${e.agent},${e.action},"${e.details}"`
    );
    res.setHeader('Content-Type', 'text/csv');
    return res.send([header, ...rows].join('\n'));
  }

  res.json({ events: auditEvents });
});

// Aggregated stats — tries Python bridge first
router.get('/api/audit/stats', async (req, res) => {
  try {
    const realData = await fetchBridge('/bridge/audit/stats');
    return res.json(realData);
  } catch {
    // Bridge unavailable — use in-memory fallback
    const bySeverity = {};
    const byAgent = {};

    for (const event of auditEvents) {
      bySeverity[event.severity] = (bySeverity[event.severity] || 0) + 1;
      byAgent[event.agent] = (byAgent[event.agent] || 0) + 1;
    }

    res.json({
      total_events: auditEvents.length,
      by_severity: bySeverity,
      by_agent: byAgent,
    });
  }
});

module.exports = router;
