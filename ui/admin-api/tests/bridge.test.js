/**
 * Tests for the Python-Node bridge.
 *
 * These tests spawn the bridge.py process, verify it responds correctly,
 * and tear it down after each suite. They require Python 3 on the PATH.
 */

const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

const BRIDGE_PORT = 17892; // use a non-default port to avoid conflicts
const BRIDGE_URL = `http://127.0.0.1:${BRIDGE_PORT}`;
const BRIDGE_SCRIPT = path.resolve(__dirname, '..', 'bridge.py');

let bridgeProcess = null;

function fetchJSON(urlPath) {
  return new Promise((resolve, reject) => {
    http.get(`${BRIDGE_URL}${urlPath}`, { timeout: 5000 }, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch {
          reject(new Error(`Invalid JSON: ${data}`));
        }
      });
    }).on('error', reject);
  });
}

function waitForBridge(retries = 30, delay = 200) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      http.get(`${BRIDGE_URL}/bridge/hardware`, { timeout: 1000 }, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => resolve());
      }).on('error', () => {
        if (attempts >= retries) {
          return reject(new Error('Bridge did not start in time'));
        }
        setTimeout(check, delay);
      });
    };
    check();
  });
}

beforeAll(async () => {
  bridgeProcess = spawn('python3', [BRIDGE_SCRIPT], {
    env: { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  // Collect stderr for debugging if needed
  bridgeProcess.stderr.on('data', () => {});

  await waitForBridge();
}, 15000);

afterAll(() => {
  if (bridgeProcess) {
    bridgeProcess.kill('SIGTERM');
    bridgeProcess = null;
  }
});

describe('Python bridge', () => {
  it('responds to /bridge/hardware with valid JSON', async () => {
    const { status, body } = await fetchJSON('/bridge/hardware');
    expect(status).toBe(200);
    expect(body.profile).toBeDefined();
    expect(body.profile.cpu_cores).toBeGreaterThan(0);
    expect(body.profile.ram_gb).toBeGreaterThan(0);
    expect(body.recommendation).toBeDefined();
    expect(body.recommendation.model_name).toBeDefined();
  });

  it('responds to /bridge/fleet/status with device data', async () => {
    const { status, body } = await fetchJSON('/bridge/fleet/status');
    expect(status).toBe(200);
    expect(body.total_devices).toBeGreaterThanOrEqual(1);
    expect(body.active_devices).toBeDefined();
    expect(body.model_distribution).toBeDefined();
    expect(body.local_hardware).toBeDefined();
  });

  it('responds to /bridge/users with user list', async () => {
    const { status, body } = await fetchJSON('/bridge/users');
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
    expect(body[0].username).toBeDefined();
    expect(body[0].provider).toBe('api_key');
  });

  it('responds to /bridge/audit with events', async () => {
    const { status, body } = await fetchJSON('/bridge/audit');
    expect(status).toBe(200);
    expect(body.total).toBeGreaterThan(0);
    expect(Array.isArray(body.events)).toBe(true);
    expect(body.events[0].event_id).toBeDefined();
    expect(body.events[0].severity).toBeDefined();
  });

  it('responds to /bridge/audit/stats with aggregations', async () => {
    const { status, body } = await fetchJSON('/bridge/audit/stats');
    expect(status).toBe(200);
    expect(body.total_events).toBeGreaterThan(0);
    expect(body.by_severity).toBeDefined();
    expect(body.by_agent).toBeDefined();
  });

  it('responds to /bridge/compliance/SOC2 with a report', async () => {
    const { status, body } = await fetchJSON('/bridge/compliance/SOC2');
    expect(status).toBe(200);
    expect(body.framework).toBe('SOC2');
    expect(body.overall_status).toBeDefined();
    expect(Array.isArray(body.controls)).toBe(true);
  });

  it('responds to /bridge/cost with cost report', async () => {
    const { status, body } = await fetchJSON('/bridge/cost');
    expect(status).toBe(200);
    expect(body.total_spent_usd).toBeDefined();
    expect(body.by_model).toBeDefined();
    expect(body.call_count).toBeGreaterThan(0);
  });

  it('responds to /bridge/workspaces with workspace list', async () => {
    const { status, body } = await fetchJSON('/bridge/workspaces');
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
    expect(body[0].name).toBeDefined();
    expect(body[0].members).toBeDefined();
  });

  it('returns 404 for unknown routes', async () => {
    const { status, body } = await fetchJSON('/bridge/nonexistent');
    expect(status).toBe(404);
    expect(body.error).toMatch(/Unknown bridge endpoint/);
  });

  it('returns 400 for unknown compliance framework', async () => {
    const { status, body } = await fetchJSON('/bridge/compliance/UNKNOWN');
    expect(status).toBe(400);
    expect(body.error).toMatch(/Unknown framework/);
  });
});
