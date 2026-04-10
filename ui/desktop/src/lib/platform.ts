/**
 * Runtime platform detection for dual-mode operation:
 * - Tauri desktop app (production)
 * - Browser via Vite dev server (development)
 */

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

/** True when running inside the Tauri WebView. */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/**
 * Base URL for API calls.
 * - In Tauri: absolute URL to the sidecar (no proxy).
 * - In browser dev: empty string (Vite proxy handles /api → localhost:7891).
 */
export function getApiBaseUrl(): string {
  if (isTauri()) {
    return 'http://127.0.0.1:7891';
  }
  return '';
}
