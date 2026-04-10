import { useState, useCallback, useEffect, useRef } from 'react';
import type { Task, Settings, ChatSession, ChatMessage } from '../types';
import { getApiBaseUrl } from '../lib/platform';

// ---------- API client ----------

const api = {
  async post(path: string, body?: any) {
    const base = getApiBaseUrl();
    const res = await fetch(`${base}/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    return res.json();
  },
  async get(path: string) {
    const base = getApiBaseUrl();
    const res = await fetch(`${base}/api${path}`);
    return res.json();
  },
  async put(path: string, body: any) {
    const base = getApiBaseUrl();
    const res = await fetch(`${base}/api${path}`, {
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
  localModel: 'gemma4:e4b',
  cloudModel: 'claude-sonnet-4',
  workspacePath: '~/workspace',
};

// ---------- Mapping helpers ----------

/** Map an API task object to our frontend Task type. */
function mapApiTaskToTask(apiTask: any): Task {
  // Extract execution summaries as subtasks if available
  const subtasks = apiTask.subtasks ?? [];
  if (subtasks.length === 0 && apiTask.result?.execution) {
    for (const exec of apiTask.result.execution) {
      subtasks.push({
        id: `${exec.agent}-${exec.action}`,
        agent: exec.agent ?? '',
        action: exec.action_performed || exec.action || '',
        status: exec.status === 'success' ? 'success' : exec.status === 'error' ? 'error' : 'pending',
        result: exec.result ?? exec.items ?? undefined,
      });
    }
  }

  return {
    id: apiTask.task_id ?? apiTask.id,
    rawInput: apiTask.input ?? '',
    intent: apiTask.input
      ? apiTask.input.length > 60
        ? apiTask.input.slice(0, 57) + '...'
        : apiTask.input
      : '',
    status: mapApiStatus(apiTask.status),
    subtasks,
    result: apiTask.result ?? undefined,
    report: apiTask.report ?? undefined,
    error: apiTask.error ?? undefined,
    costUsd: apiTask.cost_usd ?? undefined,
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
        const base = getApiBaseUrl();
        const res = await fetch(`${base}/api/health`);
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

// ---------- Streaming state ----------

export interface StreamState {
  /** Current status message shown to user */
  statusMessage: string;
  /** Text accumulated so far (streamed token by token) */
  streamedText: string;
  /** Whether we're actively streaming */
  isStreaming: boolean;
}

// ---------- Main hook ----------

export function useIntentOS() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [isLoading, setIsLoading] = useState(false);
  const [stream, setStream] = useState<StreamState>({
    statusMessage: '',
    streamedText: '',
    isStreaming: false,
  });
  const abortRef = useRef<AbortController | null>(null);

  // Session state
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  // Ref to always read latest activeSessionId inside callbacks
  const activeSessionRef = useRef<string | null>(null);
  useEffect(() => {
    activeSessionRef.current = activeSessionId;
  }, [activeSessionId]);

  // Load sessions and settings from API on mount
  useEffect(() => {
    (async () => {
      try {
        const data = await api.get('/sessions');
        if (data.sessions && Array.isArray(data.sessions)) {
          setSessions(data.sessions.map((s: any) => ({
            id: s.id,
            title: s.title,
            createdAt: new Date(s.created_at * 1000).toISOString(),
            updatedAt: new Date(s.updated_at * 1000).toISOString(),
            messageCount: s.message_count ?? 0,
          })));
        }
      } catch {
        // API unreachable
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

  const submitTask = useCallback(async (input: string, fileId?: string): Promise<Task> => {
    setIsLoading(true);
    setStream({ statusMessage: 'Connecting...', streamedText: '', isStreaming: true });

    // Create abort controller for stop button
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const base = getApiBaseUrl();
      const payload: Record<string, string> = { input };
      if (fileId) payload.file_id = fileId;
      // Always read latest session ID from ref (not stale closure)
      const currentSessionId = activeSessionRef.current;
      if (currentSessionId) payload.session_id = currentSessionId;

      const response = await fetch(`${base}/api/task/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error('Stream unavailable');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = '';
      let doneData: any = null;
      let errorMsg = '';
      let buffer = '';
      let streamFinished = false;

      while (!streamFinished) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);

              if (eventType === 'status') {
                setStream((prev) => ({
                  ...prev,
                  statusMessage: data.message || '',
                }));
              } else if (eventType === 'token') {
                accumulated += data.text || '';
                setStream((prev) => ({
                  ...prev,
                  streamedText: accumulated,
                  statusMessage: '',
                }));
              } else if (eventType === 'error') {
                errorMsg = data.message || 'Something went wrong';
              } else if (eventType === 'done') {
                doneData = data;
                streamFinished = true;
              }
            } catch {
              // skip unparseable data lines
            }
            eventType = '';
          }
        }
      }

      // Close the reader immediately so the connection doesn't hang
      try { reader.cancel(); } catch { /* ignore */ }

      // Track session — update both state and ref immediately
      const sid = doneData?.session_id;
      if (sid) {
        setActiveSessionId(sid);
        activeSessionRef.current = sid;
      }

      // Append user + assistant messages to chat history
      const now = new Date().toISOString();
      const userMsg: ChatMessage = {
        id: `u-${Date.now()}`,
        sessionId: sid || '',
        role: 'user',
        content: input,
        createdAt: now,
      };
      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        sessionId: sid || '',
        role: 'assistant',
        content: errorMsg || accumulated || 'Done.',
        costUsd: doneData?.cost_usd ?? 0,
        durationMs: doneData?.duration_ms ?? 0,
        createdAt: now,
      };
      setChatMessages((prev) => [...prev, userMsg, assistantMsg]);

      // Build task object (for backwards compat)
      const task: Task = {
        id: doneData?.task_id || `stream-${Date.now()}`,
        rawInput: input,
        intent: input.length > 60 ? input.slice(0, 57) + '...' : input,
        status: errorMsg ? 'error' : 'success',
        subtasks: [],
        report: accumulated || undefined,
        error: errorMsg || undefined,
        costUsd: doneData?.cost_usd ?? 0,
        durationMs: doneData?.duration_ms ?? 0,
        suggestions: doneData?.suggestions ?? undefined,
        createdAt: now,
      };

      setTasks((prev) => [task, ...prev]);
      setIsLoading(false);
      setStream({ statusMessage: '', streamedText: '', isStreaming: false });
      abortRef.current = null;
      refreshSessions();
      return task;
    } catch (err: any) {
      // If aborted by stop button, keep the streamed text
      if (err?.name === 'AbortError') {
        // Build a task from whatever we streamed so far
        const partial: Task = {
          id: `stopped-${Date.now()}`,
          rawInput: input,
          intent: input.length > 60 ? input.slice(0, 57) + '...' : input,
          status: 'success',
          subtasks: [],
          report: undefined, // will be set from stream state below
          createdAt: new Date().toISOString(),
        };
        // Access current stream state via a getter
        setStream((prev) => {
          if (prev.streamedText) {
            partial.report = prev.streamedText + '\n\n*(stopped)*';
          }
          return { statusMessage: '', streamedText: '', isStreaming: false };
        });
        if (partial.report) {
          setTasks((prev) => [partial, ...prev]);
        }
        setIsLoading(false);
        abortRef.current = null;
        return partial;
      }

      // API unreachable — fall back to mock
      await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));
      const task = createMockTask(input);
      setTasks((prev) => [task, ...prev]);
      setIsLoading(false);
      setStream({ statusMessage: '', streamedText: '', isStreaming: false });
      abortRef.current = null;
      return task;
    }
  }, []);

  const stopTask = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
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

  const refreshSessions = useCallback(async () => {
    try {
      const data = await api.get('/sessions');
      if (data.sessions && Array.isArray(data.sessions)) {
        setSessions(data.sessions.map((s: any) => ({
          id: s.id,
          title: s.title,
          createdAt: new Date(s.created_at * 1000).toISOString(),
          updatedAt: new Date(s.updated_at * 1000).toISOString(),
          messageCount: s.message_count ?? 0,
        })));
      }
    } catch {
      // ignore
    }
  }, []);

  const loadSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    activeSessionRef.current = sessionId;
    try {
      const data = await api.get(`/sessions/${sessionId}/messages`);
      if (data.messages && Array.isArray(data.messages)) {
        const messages: ChatMessage[] = data.messages.map((m: any) => ({
          id: m.id,
          sessionId: m.session_id,
          role: m.role,
          content: m.content,
          fileName: m.file_name,
          costUsd: m.cost_usd,
          durationMs: m.duration_ms,
          createdAt: new Date(m.created_at * 1000).toISOString(),
        }));
        setChatMessages(messages);

        // Also build tasks from messages for ResultPane display
        const taskList: Task[] = [];
        for (let i = 0; i < messages.length; i++) {
          const msg = messages[i];
          if (msg.role === 'user') {
            const reply = messages[i + 1];
            taskList.push({
              id: msg.id,
              rawInput: msg.content,
              intent: msg.content.length > 60 ? msg.content.slice(0, 57) + '...' : msg.content,
              status: 'success',
              subtasks: [],
              report: reply?.content,
              costUsd: reply?.costUsd,
              durationMs: reply?.durationMs,
              createdAt: msg.createdAt,
            });
          }
        }
        setTasks(taskList.reverse());
      }
    } catch {
      // ignore
    }
  }, []);

  const newSession = useCallback(() => {
    setActiveSessionId(null);
    activeSessionRef.current = null;
    setChatMessages([]);
    setTasks([]);
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await api.post(`/sessions/${sessionId}`, {}); // DELETE not easy with api helper
      // Use fetch directly for DELETE
      const base = getApiBaseUrl();
      await fetch(`${base}/api/sessions/${sessionId}`, { method: 'DELETE' });
      refreshSessions();
      if (activeSessionId === sessionId) {
        newSession();
      }
    } catch {
      // ignore
    }
  }, [activeSessionId, refreshSessions, newSession]);

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
    stream,
    sessions,
    activeSessionId,
    chatMessages,
    submitTask,
    stopTask,
    loadSession,
    newSession,
    deleteSession,
    getHistory,
    getSettings,
    updateSettings,
    getStatus,
    getCost,
  };
}
