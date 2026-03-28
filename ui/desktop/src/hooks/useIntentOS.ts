import { useState, useCallback } from 'react';
import type { Task, Settings } from '../types';

// ---------- Mock helpers ----------

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

// ---------- Hook ----------

export function useIntentOS() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [isLoading, setIsLoading] = useState(false);

  const submitTask = useCallback(async (input: string): Promise<Task> => {
    setIsLoading(true);
    // Simulate network latency
    await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));
    const task = createMockTask(input);
    setTasks((prev) => [task, ...prev]);
    setIsLoading(false);
    return task;
  }, []);

  const getHistory = useCallback((): Task[] => tasks, [tasks]);

  const getSettings = useCallback((): Settings => settings, [settings]);

  const updateSettings = useCallback((partial: Partial<Settings>) => {
    setSettings((prev) => ({ ...prev, ...partial }));
  }, []);

  return {
    tasks,
    settings,
    isLoading,
    submitTask,
    getHistory,
    getSettings,
    updateSettings,
  };
}
