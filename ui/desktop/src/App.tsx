import { useState, useCallback } from 'react';
import { SettingsIcon } from 'lucide-react';
import { TaskInput } from './components/TaskInput';
import { TaskHistory } from './components/TaskHistory';
import { ResultPane } from './components/ResultPane';
import { Settings } from './components/Settings';
import { StatusBar } from './components/StatusBar';
import { useIntentOS } from './hooks/useIntentOS';
import type { Task } from './types';
import './App.css';

function App() {
  const { tasks, settings, isLoading, submitTask, updateSettings } = useIntentOS();
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleSubmit = useCallback(
    async (input: string) => {
      const task = await submitTask(input);
      setSelectedTask(task);
    },
    [submitTask],
  );

  const handleSelectTask = useCallback(
    (taskId: string) => {
      const task = tasks.find((t) => t.id === taskId) ?? null;
      setSelectedTask(task);
    },
    [tasks],
  );

  return (
    <div className="app">
      <header className="app__header">
        <h1 className="app__logo">IntentOS</h1>
        <button
          className="app__settings-btn"
          onClick={() => setSettingsOpen(true)}
          aria-label="Open settings"
        >
          <SettingsIcon size={18} />
        </button>
      </header>

      <div className="app__body">
        <TaskHistory
          tasks={tasks}
          onSelect={handleSelectTask}
          selectedId={selectedTask?.id}
        />
        <main className="app__main">
          <ResultPane task={selectedTask} />
        </main>
      </div>

      <TaskInput onSubmit={handleSubmit} isLoading={isLoading} />

      <StatusBar
        settings={settings}
        tokensUsed={0}
        tokenBudget={100000}
      />

      <Settings
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onUpdate={updateSettings}
      />
    </div>
  );
}

export default App;
