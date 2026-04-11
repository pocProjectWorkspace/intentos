import { useState, useCallback } from 'react';
import { SettingsIcon } from 'lucide-react';
import { TaskInput } from './components/TaskInput';
import { TaskHistory } from './components/TaskHistory';
import { ResultPane } from './components/ResultPane';
import { Settings } from './components/Settings';
import { StatusBar } from './components/StatusBar';
import { SetupWizard } from './components/SetupWizard';
import { isTauri } from './lib/platform';
import { useIntentOS } from './hooks/useIntentOS';
import './App.css';

function App() {
  const [setupComplete, setSetupComplete] = useState(!isTauri());

  const {
    tasks, settings, isLoading, stream,
    sessions, activeSessionId, chatMessages,
    submitTask, stopTask, updateSettings,
    loadSession, newSession, deleteSession,
  } = useIntentOS();
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Get the latest task (for suggestions display)
  const latestTask = tasks[0] ?? null;

  const handleSubmit = useCallback(
    async (input: string, fileId?: string) => {
      await submitTask(input, fileId);
    },
    [submitTask],
  );

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      await loadSession(sessionId);
    },
    [loadSession],
  );

  if (!setupComplete) {
    return <SetupWizard onComplete={() => setSetupComplete(true)} />;
  }

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
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelect={() => {}}
          onSelectSession={handleSelectSession}
          onNewSession={newSession}
          onDeleteSession={deleteSession}
        />
        <main className="app__main">
          <ResultPane
            task={latestTask}
            stream={stream}
            chatMessages={chatMessages}
            onSuggestionClick={handleSubmit}
          />
        </main>
      </div>

      <TaskInput onSubmit={handleSubmit} isLoading={isLoading} onStop={stopTask} />

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
