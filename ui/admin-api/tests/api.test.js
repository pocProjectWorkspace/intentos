const request = require('supertest');
const app = require('../src/index');

const AUTH = { Authorization: 'Bearer test-token-123' };

// Reset in-memory stores between tests
beforeEach(() => {
  const userRoutes = require('../src/routes/users');
  const policyRoutes = require('../src/routes/policies');
  userRoutes._store.reset();
  policyRoutes._store.reset();
});

// --- Health ---

describe('GET /api/health', () => {
  it('returns 200 with status ok', async () => {
    const res = await request(app).get('/api/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('ok');
    expect(res.body.version).toBe('0.1.0');
    expect(typeof res.body.uptime_seconds).toBe('number');
  });
});

// --- Auth middleware ---

describe('Auth middleware', () => {
  it('rejects requests without Authorization header', async () => {
    const res = await request(app).get('/api/users');
    expect(res.status).toBe(401);
    expect(res.body.error).toMatch(/Authorization/i);
  });

  it('rejects requests with empty Bearer token', async () => {
    const res = await request(app)
      .get('/api/users')
      .set('Authorization', 'Bearer ');
    expect(res.status).toBe(401);
  });

  it('accepts requests with a valid token', async () => {
    const res = await request(app)
      .get('/api/users')
      .set(AUTH);
    expect(res.status).toBe(200);
  });
});

// --- Users ---

describe('Users CRUD', () => {
  it('lists users (initially empty)', async () => {
    const res = await request(app).get('/api/users').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it('creates a user', async () => {
    const res = await request(app)
      .post('/api/users')
      .set(AUTH)
      .send({ username: 'alice', email: 'alice@test.com', role: 'admin' });
    expect(res.status).toBe(201);
    expect(res.body.username).toBe('alice');
    expect(res.body.id).toBeDefined();
  });

  it('returns 400 when required fields are missing', async () => {
    const res = await request(app)
      .post('/api/users')
      .set(AUTH)
      .send({ username: 'bob' });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/required/i);
  });

  it('gets a user by id', async () => {
    const create = await request(app)
      .post('/api/users')
      .set(AUTH)
      .send({ username: 'carol', email: 'carol@test.com', role: 'viewer' });
    const res = await request(app)
      .get(`/api/users/${create.body.id}`)
      .set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.username).toBe('carol');
  });

  it('returns 404 for non-existent user', async () => {
    const res = await request(app).get('/api/users/999').set(AUTH);
    expect(res.status).toBe(404);
  });

  it('updates a user', async () => {
    const create = await request(app)
      .post('/api/users')
      .set(AUTH)
      .send({ username: 'dave', email: 'dave@test.com', role: 'editor' });
    const res = await request(app)
      .put(`/api/users/${create.body.id}`)
      .set(AUTH)
      .send({ role: 'admin' });
    expect(res.status).toBe(200);
    expect(res.body.role).toBe('admin');
    expect(res.body.updated_at).toBeDefined();
  });

  it('deletes a user', async () => {
    const create = await request(app)
      .post('/api/users')
      .set(AUTH)
      .send({ username: 'eve', email: 'eve@test.com', role: 'viewer' });
    const del = await request(app)
      .delete(`/api/users/${create.body.id}`)
      .set(AUTH);
    expect(del.status).toBe(204);

    const get = await request(app)
      .get(`/api/users/${create.body.id}`)
      .set(AUTH);
    expect(get.status).toBe(404);
  });
});

// --- Policies ---

describe('Policies CRUD', () => {
  it('lists policies (initially empty)', async () => {
    const res = await request(app).get('/api/policies').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it('creates a policy', async () => {
    const res = await request(app)
      .post('/api/policies')
      .set(AUTH)
      .send({ name: 'strict', sandbox_tier: 'tier-3', network_allowed: false, allowed_domains: [] });
    expect(res.status).toBe(201);
    expect(res.body.name).toBe('strict');
    expect(res.body.sandbox_tier).toBe('tier-3');
  });

  it('returns 400 when required fields are missing', async () => {
    const res = await request(app)
      .post('/api/policies')
      .set(AUTH)
      .send({ name: 'incomplete' });
    expect(res.status).toBe(400);
  });

  it('updates a policy', async () => {
    const create = await request(app)
      .post('/api/policies')
      .set(AUTH)
      .send({ name: 'relaxed', sandbox_tier: 'tier-1' });
    const res = await request(app)
      .put(`/api/policies/${create.body.id}`)
      .set(AUTH)
      .send({ network_allowed: true, allowed_domains: ['example.com'] });
    expect(res.status).toBe(200);
    expect(res.body.network_allowed).toBe(true);
    expect(res.body.allowed_domains).toEqual(['example.com']);
  });

  it('deletes a policy', async () => {
    const create = await request(app)
      .post('/api/policies')
      .set(AUTH)
      .send({ name: 'temp', sandbox_tier: 'tier-2' });
    const del = await request(app)
      .delete(`/api/policies/${create.body.id}`)
      .set(AUTH);
    expect(del.status).toBe(204);
  });
});

// --- Audit ---

describe('Audit endpoints', () => {
  it('lists audit events', async () => {
    const res = await request(app).get('/api/audit').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.total).toBeGreaterThan(0);
    expect(Array.isArray(res.body.events)).toBe(true);
  });

  it('filters audit events by severity', async () => {
    const res = await request(app).get('/api/audit?severity=error').set(AUTH);
    expect(res.status).toBe(200);
    res.body.events.forEach((e) => expect(e.severity).toBe('error'));
  });

  it('filters audit events by agent', async () => {
    const res = await request(app).get('/api/audit?agent=agent-alpha').set(AUTH);
    expect(res.status).toBe(200);
    res.body.events.forEach((e) => expect(e.agent).toBe('agent-alpha'));
  });

  it('respects limit and offset', async () => {
    const res = await request(app).get('/api/audit?limit=2&offset=1').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.events.length).toBeLessThanOrEqual(2);
    expect(res.body.offset).toBe(1);
  });

  it('exports as JSON', async () => {
    const res = await request(app).get('/api/audit/export?format=json').set(AUTH);
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body.events)).toBe(true);
  });

  it('exports as CSV', async () => {
    const res = await request(app).get('/api/audit/export?format=csv').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toMatch(/text\/csv/);
    expect(res.text).toContain('id,timestamp,severity');
  });

  it('returns audit stats', async () => {
    const res = await request(app).get('/api/audit/stats').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.total_events).toBeGreaterThan(0);
    expect(res.body.by_severity).toBeDefined();
    expect(res.body.by_agent).toBeDefined();
  });
});

// --- Fleet ---

describe('Fleet endpoints', () => {
  it('returns fleet status', async () => {
    const res = await request(app).get('/api/fleet/status').set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.total_devices).toBeGreaterThan(0);
    expect(res.body.active_devices).toBeDefined();
    expect(res.body.model_distribution).toBeDefined();
  });

  it('lists devices', async () => {
    const res = await request(app).get('/api/fleet/devices').set(AUTH);
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body[0].hardware).toBeDefined();
  });

  it('triggers deployment', async () => {
    const res = await request(app)
      .post('/api/fleet/deploy')
      .set(AUTH)
      .send({ device_group: 'workstations', version: '0.2.0' });
    expect(res.status).toBe(202);
    expect(res.body.deployment_id).toBeDefined();
    expect(res.body.status).toBe('queued');
  });

  it('returns 400 for deployment with missing fields', async () => {
    const res = await request(app)
      .post('/api/fleet/deploy')
      .set(AUTH)
      .send({ device_group: 'workstations' });
    expect(res.status).toBe(400);
  });

  it('lists available updates', async () => {
    const res = await request(app).get('/api/fleet/updates').set(AUTH);
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
  });
});

// --- 404 ---

describe('Unknown routes', () => {
  it('returns 404 for unknown routes', async () => {
    const res = await request(app).get('/api/nonexistent').set(AUTH);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });
});
