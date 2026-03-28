const { Router } = require('express');

const router = Router();

// In-memory store
const policies = [];
let nextId = 1;

// List all policies
router.get('/api/policies', (req, res) => {
  res.json(policies);
});

// Create policy
router.post('/api/policies', (req, res) => {
  const { name, sandbox_tier, network_allowed, allowed_domains } = req.body;

  if (!name || !sandbox_tier) {
    return res.status(400).json({ error: 'Missing required fields: name, sandbox_tier' });
  }

  const policy = {
    id: nextId++,
    name,
    sandbox_tier,
    network_allowed: network_allowed || false,
    allowed_domains: allowed_domains || [],
    created_at: new Date().toISOString(),
  };
  policies.push(policy);
  res.status(201).json(policy);
});

// Update policy
router.put('/api/policies/:id', (req, res) => {
  const policy = policies.find((p) => p.id === parseInt(req.params.id, 10));
  if (!policy) {
    return res.status(404).json({ error: 'Policy not found' });
  }

  const { name, sandbox_tier, network_allowed, allowed_domains } = req.body;
  if (name !== undefined) policy.name = name;
  if (sandbox_tier !== undefined) policy.sandbox_tier = sandbox_tier;
  if (network_allowed !== undefined) policy.network_allowed = network_allowed;
  if (allowed_domains !== undefined) policy.allowed_domains = allowed_domains;
  policy.updated_at = new Date().toISOString();

  res.json(policy);
});

// Delete policy
router.delete('/api/policies/:id', (req, res) => {
  const index = policies.findIndex((p) => p.id === parseInt(req.params.id, 10));
  if (index === -1) {
    return res.status(404).json({ error: 'Policy not found' });
  }

  policies.splice(index, 1);
  res.status(204).send();
});

// Export for testing cleanup
router._store = { policies, reset: () => { policies.length = 0; nextId = 1; } };

module.exports = router;
