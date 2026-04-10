import { useState, useEffect } from 'react';
import { isTauri } from '../lib/platform';
import type { PullProgress, OllamaStatus } from '../lib/tauri-api';

interface SetupWizardProps {
  onComplete: () => void;
}

type SetupStage =
  | 'checking'
  | 'needs-setup'
  | 'installing'
  | 'pulling'
  | 'ready'
  | 'error';

const STAGE_LABELS: Record<string, string> = {
  checking: 'Checking your system...',
  'needs-setup': '',
  installing: 'Installing local AI engine...',
  pulling: 'Downloading your local AI...',
  ready: 'IntentOS is ready.',
  error: 'Something went wrong.',
};

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const [stage, setStage] = useState<SetupStage>('checking');
  const [progress, setProgress] = useState<PullProgress | null>(null);
  const [error, setError] = useState('');
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);

  useEffect(() => {
    if (!isTauri()) {
      // Browser dev mode — skip setup
      onComplete();
      return;
    }

    let cancelled = false;

    async function checkStatus() {
      try {
        const { getBackendStatus, onPullProgress, onOllamaStatusChange } =
          await import('../lib/tauri-api');

        // Listen for pull progress
        onPullProgress((p) => {
          if (!cancelled) setProgress(p);
        });

        // Listen for Ollama status changes
        onOllamaStatusChange((status) => {
          if (cancelled) return;
          if (status === 'installing') setStage('installing');
          else if (status === 'pulling' || status === 'pulling-embeddings') setStage('pulling');
          else if (status === 'ready') {
            setStage('ready');
            setTimeout(onComplete, 1500);
          }
        });

        const status = await getBackendStatus();
        if (!cancelled) {
          setOllamaStatus(status.ollama);

          if (status.backend_alive && status.ollama.models.length > 0) {
            // Already set up
            onComplete();
          } else if (!status.ollama.installed || status.ollama.models.length === 0) {
            setStage('needs-setup');
          } else {
            // Ollama installed with models, just waiting for backend
            onComplete();
          }
        }
      } catch {
        if (!cancelled) {
          // Backend not ready yet — wait and retry
          setTimeout(checkStatus, 2000);
        }
      }
    }

    checkStatus();

    return () => {
      cancelled = true;
    };
  }, [onComplete]);

  async function handleSetup() {
    try {
      setStage('installing');
      const { setupOllama, getPlatformInfo } = await import('../lib/tauri-api');

      // For now, use a default model. The backend will detect hardware.
      await setupOllama('llama3.1:8b');
      setStage('ready');
      setTimeout(onComplete, 1500);
    } catch (e) {
      setStage('error');
      setError(String(e));
    }
  }

  function handleSkip() {
    onComplete();
  }

  const progressBar =
    progress && progress.percent > 0 ? (
      <div className="setup-progress">
        <div className="setup-progress__bar">
          <div
            className="setup-progress__fill"
            style={{ width: `${Math.min(progress.percent, 100)}%` }}
          />
        </div>
        <span className="setup-progress__text">
          {progress.percent.toFixed(0)}%
        </span>
      </div>
    ) : null;

  return (
    <div className="setup-wizard">
      <div className="setup-wizard__card">
        <h1 className="setup-wizard__title">IntentOS</h1>
        <p className="setup-wizard__subtitle">
          Your computer, finally on your side.
        </p>

        {stage === 'checking' && (
          <p className="setup-wizard__status">{STAGE_LABELS.checking}</p>
        )}

        {stage === 'needs-setup' && (
          <div className="setup-wizard__choices">
            <p>IntentOS can run AI entirely on your device.</p>
            <p>This requires a one-time download (~2 GB).</p>
            <div className="setup-wizard__buttons">
              <button className="setup-wizard__btn--primary" onClick={handleSetup}>
                Set up local AI
              </button>
              <button className="setup-wizard__btn--secondary" onClick={handleSkip}>
                Skip for now
              </button>
            </div>
          </div>
        )}

        {(stage === 'installing' || stage === 'pulling') && (
          <div className="setup-wizard__progress">
            <p className="setup-wizard__status">{STAGE_LABELS[stage]}</p>
            {progressBar}
            <p className="setup-wizard__hint">
              This happens once. After this, IntentOS works instantly — even
              without an internet connection.
            </p>
          </div>
        )}

        {stage === 'ready' && (
          <p className="setup-wizard__status setup-wizard__status--success">
            {STAGE_LABELS.ready}
          </p>
        )}

        {stage === 'error' && (
          <div className="setup-wizard__error">
            <p className="setup-wizard__status setup-wizard__status--error">
              {STAGE_LABELS.error}
            </p>
            <p>{error}</p>
            <div className="setup-wizard__buttons">
              <button className="setup-wizard__btn--primary" onClick={handleSetup}>
                Try again
              </button>
              <button className="setup-wizard__btn--secondary" onClick={handleSkip}>
                Skip for now
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
