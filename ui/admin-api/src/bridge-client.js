/**
 * Bridge client — fetches data from the Python bridge server.
 *
 * The Express API calls fetchBridge() to get real data from Python modules.
 * If the bridge is unreachable, callers fall back to in-memory mock data.
 */

const http = require('http');

const BRIDGE_URL = process.env.BRIDGE_URL || 'http://127.0.0.1:7892';

/**
 * Fetch JSON from the Python bridge.
 * @param {string} path - Bridge endpoint path (e.g. "/bridge/fleet/status")
 * @returns {Promise<object>} Parsed JSON response
 */
async function fetchBridge(path) {
  return new Promise((resolve, reject) => {
    const url = `${BRIDGE_URL}${path}`;
    const req = http.get(url, { timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        if (res.statusCode >= 400) {
          return reject(new Error(`Bridge returned ${res.statusCode}: ${data}`));
        }
        try {
          resolve(JSON.parse(data));
        } catch {
          reject(new Error('Invalid JSON from bridge'));
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Bridge request timed out'));
    });
  });
}

module.exports = { fetchBridge, BRIDGE_URL };
