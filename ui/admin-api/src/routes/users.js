const { Router } = require('express');
const { fetchBridge } = require('../bridge-client');

const router = Router();

// In-memory store
const users = [];
let nextId = 1;

// List all users — tries Python bridge first for real auth users
router.get('/api/users', async (req, res) => {
  try {
    const bridgeUsers = await fetchBridge('/bridge/users');
    // Merge bridge users with any locally-created users
    const merged = [...bridgeUsers, ...users];
    return res.json(merged);
  } catch {
    // Bridge unavailable — use in-memory fallback
    res.json(users);
  }
});

// Get user by id
router.get('/api/users/:id', (req, res) => {
  const user = users.find((u) => u.id === parseInt(req.params.id, 10));
  if (!user) {
    return res.status(404).json({ error: 'User not found' });
  }
  res.json(user);
});

// Create user
router.post('/api/users', (req, res) => {
  const { username, email, role } = req.body;

  if (!username || !email || !role) {
    return res.status(400).json({ error: 'Missing required fields: username, email, role' });
  }

  const user = {
    id: nextId++,
    username,
    email,
    role,
    created_at: new Date().toISOString(),
  };
  users.push(user);
  res.status(201).json(user);
});

// Update user
router.put('/api/users/:id', (req, res) => {
  const user = users.find((u) => u.id === parseInt(req.params.id, 10));
  if (!user) {
    return res.status(404).json({ error: 'User not found' });
  }

  const { username, email, role } = req.body;
  if (username) user.username = username;
  if (email) user.email = email;
  if (role) user.role = role;
  user.updated_at = new Date().toISOString();

  res.json(user);
});

// Delete user
router.delete('/api/users/:id', (req, res) => {
  const index = users.findIndex((u) => u.id === parseInt(req.params.id, 10));
  if (index === -1) {
    return res.status(404).json({ error: 'User not found' });
  }

  users.splice(index, 1);
  res.status(204).send();
});

// Export for testing cleanup
router._store = { users, reset: () => { users.length = 0; nextId = 1; } };

module.exports = router;
