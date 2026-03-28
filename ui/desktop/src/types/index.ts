export interface Task {
  id: string;
  rawInput: string;
  intent: string;
  status: 'pending' | 'executing' | 'success' | 'error';
  subtasks: Subtask[];
  result?: any;
  error?: string;
  durationMs?: number;
  createdAt: string;
}

export interface Subtask {
  id: string;
  agent: string;
  action: string;
  status: 'pending' | 'running' | 'success' | 'error' | 'skipped';
  result?: any;
}

export interface Settings {
  privacyMode: 'local_only' | 'smart_routing' | 'performance';
  localModel: string;
  cloudModel: string;
  workspacePath: string;
}

export interface HardwareProfile {
  gpu: { vendor: string; model: string; vramGb: number } | null;
  ramGb: number;
  cpuCores: number;
  platform: string;
}
