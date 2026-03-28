const express = require('express');
const cors = require('cors');
const helmet = require('helmet');

const authMiddleware = require('./middleware/auth');
const healthRoutes = require('./routes/health');
const userRoutes = require('./routes/users');
const policyRoutes = require('./routes/policies');
const auditRoutes = require('./routes/audit');
const fleetRoutes = require('./routes/fleet');

const app = express();

// Global middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// Health check is public (no auth)
app.use(healthRoutes);

// All other routes require auth
app.use(authMiddleware);
app.use(userRoutes);
app.use(policyRoutes);
app.use(auditRoutes);
app.use(fleetRoutes);

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

// Error handler
app.use((err, req, res, _next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

module.exports = app;
