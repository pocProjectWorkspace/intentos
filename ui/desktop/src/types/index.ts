export interface Task {
  id: string;
  rawInput: string;
  intent: string;
  status: 'pending' | 'executing' | 'success' | 'error';
  subtasks: Subtask[];
  result?: any;
  report?: string;
  error?: string;
  costUsd?: number;
  durationMs?: number;
  suggestions?: string[];
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

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: 'user' | 'assistant';
  content: string;
  fileName?: string;
  costUsd?: number;
  durationMs?: number;
  createdAt: string;
}

export interface HardwareProfile {
  gpu: { vendor: string; model: string; vramGb: number } | null;
  ramGb: number;
  cpuCores: number;
  platform: string;
}
