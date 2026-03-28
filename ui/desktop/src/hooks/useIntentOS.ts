import { useState, useCallback, useEffect } from 'react';
import type { Task, Settings } from '../types';

// ---------- API client ----------

const api = {
  async post(path: string, body?: any) {
    const res = await fetch(`/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    return res.json();
  },
  async get(path: string) {
    const res = await fetch(`/api${path}`);
    return res.json();
  },
  async put(path: string, body: any) {
    const res = await fetch(`/api${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.json();
  },
};

// ---------- Mock helpers (fallback when API is unreachable) ----------

let nextId = 1;

function mockSubtasks(): Task['subtasks'] {
  return [
    { id: `st-${nextId}-1`, agent: 'planner', action: 'Decompose intent', status: 'success' },
    { id: `st-${nextId}-2`, agent: 'coder', action: 'Generate implementation', status: 'success' },
    { id: `st-${nextId}-3`, agent: 'reviewer', action: 'Validate output', status: 'success' },
  ];
}

function createMockTask(input: string): Task {
  const id = `task-${nextId++}`;
  return {
    id,
    rawInput: input,
    intent: input.length > 60 ? input.slice(0, 57) + '...' : input,
    status: 'success',
    subtasks: mockSubtasks(),
    result: { message: `Mock result for: "${input}"` },
    durationMs: Math.floor(Math.random() * 2000) + 200,
    createdAt: new Date().toISOString(),
  };
}

const defaultSettings: Settings = {
  privacyMode: 'smart_routing',
  localModel: 'llama-3.1-8b',
  cloudModel: 'claude-sonnet-4',
  workspacePath: '~/workspace',
};

// ---------- Mapping helpers ----------

/** Map an API task object to our frontend Task type. */
function mapApiTaskToTask(apiTask: any): Task {
  return {
    id: apiTask.task_id ?? apiTask.id,
    rawInput: apiTask.input ?? '',
    intent: apiTask.input
      ? apiTask.input.length > 60
        ? apiTask.input.slice(0, 57) + '...'
        : apiTask.input
      : '',
    status: mapApiStatus(apiTask.status),
    subtasks: apiTask.subtasks ?? [],
    result: apiTask.result ?? undefined,
    error: apiTask.error ?? undefined,
    durationMs: apiTask.duration_ms ?? undefined,
    createdAt: apiTask.created_at
      ? typeof apiTask.created_at === 'number'
        ? new Date(apiTask.created_at * 1000).toISOString()
        : apiTask.created_at
      : new Date().toISOString(),
  };
}

function mapApiStatus(status: string): Task['status'] {
  switch (status) {
    case 'accepted':
    case 'pending':
      return 'pending';
    case 'executing':
    case 'running':
      return 'executing';
    case 'success':
    case 'completed':
      return 'success';
    case 'error':
    case 'failed':
      return 'error';
    default:
      return 'pending';
  }
}

/** Map API settings to frontend Settings type. */
function mapApiSettings(raw: any): Settings {
  return {
    privacyMode: mapPrivacyMode(raw.privacy_mode ?? raw.privacyMode ?? 'smart_routing'),
    localModel: raw.local_model ?? raw.localModel ?? defaultSettings.localModel,
    cloudModel: raw.cloud_model ?? raw.cloudModel ?? raw.model ?? defaultSettings.cloudModel,
    workspacePath: raw.workspace_path ?? raw.workspacePath ?? defaultSettings.workspacePath,
  };
}

function mapPrivacyMode(mode: string): Settings['privacyMode'] {
  if (mode === 'local_only' || mode === 'smart_routing' || mode === 'performance') {
    return mode;
  }
  // Map API values like "standard" to our enum
  if (mode === 'standard') return 'smart_routing';
  return 'smart_routing';
}

// ---------- API status hook ----------

export function useApiStatus() {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch('/api/health');
        setConnected(res.ok);
      } catch {
        setConnected(false);
      }
    };
    check();
    const interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, []);

  return connected;
}

// ---------- Main hook ----------

export function useIntentOS() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [isLoading, setIsLoading] = useState(false);

  // Load history and settings from API on mount
  useEffect(() => {
    (async () => {
      try {
        const data = await api.get('/history');
        if (data.tasks && Array.isArray(data.tasks)) {
          setTasks(data.tasks.map(mapApiTaskToTask));
        }
      } catch {
        // API unreachable — keep empty task list
      }
    })();

    (async () => {
      try {
        const data = await api.get('/settings');
        if (data && typeof data === 'object' && !data.error) {
          setSettings(mapApiSettings(data));
        }
      } catch {
        // API unreachable — keep default settings
      }
    })();
  }, []);

  const submitTask = useCallback(async (input: string): Promise<Task> => {
    setIsLoading(true);
    try {
      // Submit to real API
      const submitRes = await api.post('/task', { input });
      const taskId = submitRes.task_id;

      if (!taskId) {
        throw new Error('No task_id in response');
      }

      // Poll until status is no longer pending/accepted
      let taskData = submitRes;
      const maxPolls = 60;
      let polls = 0;

      while (polls < maxPolls) {
        const pollRes = await api.get(`/task/${taskId}`);
        taskData = pollRes;
        const status = pollRes.status;

        if (status !== 'pending' && status !== 'accepted' && status !== 'executing' && status !== 'running') {
          break;
        }

        // Wait before next poll
        await new Promise((r) => setTimeout(r, 1000));
        polls++;
      }

      const task = mapApiTaskToTask(taskData);
      setTasks((prev) => [task, ...prev]);
      setIsLoading(false);
      return task;
    } catch {
      // API unreachable — fall back to mock
      await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));
      const task = createMockTask(input);
      setTasks((prev) => [task, ...prev]);
      setIsLoading(false);
      return task;
    }
  }, []);

  const getHistory = useCallback(async (): Promise<Task[]> => {
    try {
      const data = await api.get('/history');
      if (data.tasks && Array.isArray(data.tasks)) {
        const mapped = data.tasks.map(mapApiTaskToTask);
        setTasks(mapped);
        return mapped;
      }
    } catch {
      // API unreachable — return current state
    }
    return tasks;
  }, [tasks]);

  const getSettings = useCallback(async (): Promise<Settings> => {
    try {
      const data = await api.get('/settings');
      if (data && typeof data === 'object' && !data.error) {
        const mapped = mapApiSettings(data);
        setSettings(mapped);
        return mapped;
      }
    } catch {
      // API unreachable — return current state
    }
    return settings;
  }, [settings]);

  const updateSettings = useCallback(async (partial: Partial<Settings>) => {
    // Update local state immediately for responsiveness
    setSettings((prev) => ({ ...prev, ...partial }));

    try {
      // Send to API with snake_case keys
      const apiPayload: Record<string, any> = {};
      if (partial.privacyMode !== undefined) apiPayload.privacy_mode = partial.privacyMode;
      if (partial.localModel !== undefined) apiPayload.local_model = partial.localModel;
      if (partial.cloudModel !== undefined) apiPayload.cloud_model = partial.cloudModel;
      if (partial.workspacePath !== undefined) apiPayload.workspace_path = partial.workspacePath;

      await api.put('/settings', apiPayload);
    } catch {
      // API unreachable — local state already updated
    }
  }, []);

  const getStatus = useCallback(async () => {
    try {
      return await api.get('/status');
    } catch {
      return null;
    }
  }, []);

  const getCost = useCallback(async () => {
    try {
      return await api.get('/cost');
    } catch {
      return null;
    }
  }, []);

  return {
    tasks,
    settings,
    isLoading,
    submitTask,
    getHistory,
    getSettings,
    updateSettings,
    getStatus,
    getCost,
  };
}
