/**
 * Typed wrappers for Tauri IPC commands.
 *
 * These are only called when isTauri() is true, so the @tauri-apps/api
 * import is safe (it's available in the Tauri WebView context).
 */

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

// -- Types matching Rust structs --

export interface OllamaStatus {
  installed: boolean;
  running: boolean;
  version: string;
  models: string[];
}

export interface BackendStatus {
  backend_alive: boolean;
  ollama: OllamaStatus;
}

export interface PullProgress {
  model: string;
  status: string; // "downloading" | "verifying" | "complete"
  percent: number;
}

export interface PlatformInfo {
  os: string;
  arch: string;
  app_version: string;
}

// -- IPC wrappers --

export function getBackendStatus(): Promise<BackendStatus> {
  return invoke('get_backend_status');
}

export function restartBackend(): Promise<void> {
  return invoke('restart_backend');
}

export function getOllamaStatus(): Promise<OllamaStatus> {
  return invoke('get_ollama_status');
}

export function setupOllama(modelName: string): Promise<void> {
  return invoke('setup_ollama', { modelName });
}

export function getPlatformInfo(): Promise<PlatformInfo> {
  return invoke('get_platform_info');
}

export function openLogsFolder(): Promise<void> {
  return invoke('open_logs_folder');
}

// -- Event listeners --

export function onPullProgress(
  callback: (progress: PullProgress) => void,
): Promise<UnlistenFn> {
  return listen<PullProgress>('ollama://pull-progress', (event) => {
    callback(event.payload);
  });
}

export function onBackendReady(
  callback: () => void,
): Promise<UnlistenFn> {
  return listen<boolean>('backend://ready', () => callback());
}

export function onBackendError(
  callback: (error: string) => void,
): Promise<UnlistenFn> {
  return listen<string>('backend://error', (event) => callback(event.payload));
}

export function onOllamaStatusChange(
  callback: (status: string) => void,
): Promise<UnlistenFn> {
  return listen<string>('ollama://status', (event) => callback(event.payload));
}
