const { Router } = require('express');
const { fetchBridge } = require('../bridge-client');

const router = Router();

// In-memory seed data (fallback when bridge is unavailable)
const devices = [
  { id: 'd-001', hostname: 'workstation-1', os: 'macOS 15.3', hardware: { cpu: 'M4 Pro', ram_gb: 32, gpu: 'Apple M4 Pro' }, status: 'online', model: 'llama-3.1-70b' },
  { id: 'd-002', hostname: 'workstation-2', os: 'Ubuntu 24.04', hardware: { cpu: 'Ryzen 9 7950X', ram_gb: 64, gpu: 'RTX 4090' }, status: 'online', model: 'mistral-7b' },
  { id: 'd-003', hostname: 'edge-node-1', os: 'Ubuntu 24.04', hardware: { cpu: 'Xeon W-2455X', ram_gb: 128, gpu: 'A100 80GB' }, status: 'offline', model: 'llama-3.1-70b' },
  { id: 'd-004', hostname: 'laptop-1', os: 'Windows 11', hardware: { cpu: 'i9-14900K', ram_gb: 32, gpu: 'RTX 4080' }, status: 'online', model: 'phi-3-mini' },
];

const updates = [
  { id: 'upd-001', version: '0.2.0', release_date: '2026-03-25', changelog: 'Sandbox tier 3 support', applicable_devices: ['d-001', 'd-002'] },
  { id: 'upd-002', version: '0.2.1', release_date: '2026-03-27', changelog: 'Security patch for policy engine', applicable_devices: ['d-001', 'd-002', 'd-003', 'd-004'] },
];

// Fleet overview — tries Python bridge first, falls back to in-memory
router.get('/api/fleet/status', async (req, res) => {
  try {
    const realData = await fetchBridge('/bridge/fleet/status');
    return res.json(realData);
  } catch {
    // Bridge unavailable — use in-memory fallback
    const activeDevices = devices.filter((d) => d.status === 'online').length;
    const modelDist = {};
    for (const d of devices) {
      modelDist[d.model] = (modelDist[d.model] || 0) + 1;
    }

    res.json({
      active_devices: activeDevices,
      total_devices: devices.length,
      model_distribution: modelDist,
    });
  }
});

// List all devices
router.get('/api/fleet/devices', (req, res) => {
  res.json(devices);
});

// Trigger deployment
router.post('/api/fleet/deploy', (req, res) => {
  const { device_group, version } = req.body;

  if (!device_group || !version) {
    return res.status(400).json({ error: 'Missing required fields: device_group, version' });
  }

  res.status(202).json({
    deployment_id: `deploy-${Date.now()}`,
    device_group,
    version,
    status: 'queued',
    queued_at: new Date().toISOString(),
  });
});

// List available updates
router.get('/api/fleet/updates', (req, res) => {
  res.json(updates);
});

module.exports = router;
