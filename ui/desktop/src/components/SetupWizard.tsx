import { useState, useEffect, useRef } from 'react';

interface SetupWizardProps {
  onComplete: () => void;
}

type Stage = 'loading' | 'no-ollama' | 'timeout';

const HEALTH_URL = 'http://127.0.0.1:7891/api/health';
const OLLAMA_URL = 'http://localhost:11434/api/tags';
const MAX_ATTEMPTS = 30;
const POLL_INTERVAL = 2000;

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const [stage, setStage] = useState<Stage>('loading');
  const attemptRef = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    attemptRef.current = 0;

    async function poll() {
      while (!cancelledRef.current && attemptRef.current < MAX_ATTEMPTS) {
        attemptRef.current += 1;
        try {
          const res = await fetch(HEALTH_URL);
          if (res.ok && !cancelledRef.current) {
            // Backend is alive — check Ollama
            try {
              const ollamaRes = await fetch(OLLAMA_URL);
              if (ollamaRes.ok) {
                onComplete();
                return;
              }
            } catch {
              // Ollama not running
            }
            if (!cancelledRef.current) {
              setStage('no-ollama');
            }
            return;
          }
        } catch {
          // Backend not ready yet
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL));
      }

      // Exhausted attempts
      if (!cancelledRef.current) {
        setStage('timeout');
      }
    }

    poll();

    return () => {
      cancelledRef.current = true;
    };
  }, [onComplete]);

  function handleRetry() {
    attemptRef.current = 0;
    cancelledRef.current = false;
    setStage('loading');
    // Re-trigger the effect by forcing a state change — the effect depends on onComplete
    // which is stable, so we manually restart polling here.
    (async () => {
      while (!cancelledRef.current && attemptRef.current < MAX_ATTEMPTS) {
        attemptRef.current += 1;
        try {
          const res = await fetch(HEALTH_URL);
          if (res.ok && !cancelledRef.current) {
            try {
              const ollamaRes = await fetch(OLLAMA_URL);
              if (ollamaRes.ok) {
                onComplete();
                return;
              }
            } catch {
              // Ollama not running
            }
            if (!cancelledRef.current) {
              setStage('no-ollama');
            }
            return;
          }
        } catch {
          // Backend not ready yet
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL));
      }
      if (!cancelledRef.current) {
        setStage('timeout');
      }
    })();
  }

  return (
    <div className="setup-wizard">
      <div className="setup-wizard__card">
        <h1 className="setup-wizard__title">IntentOS</h1>

        {stage === 'loading' && (
          <div className="setup-wizard__loading">
            <div className="setup-wizard__spinner" />
            <p className="setup-wizard__status">Starting IntentOS...</p>
          </div>
        )}

        {stage === 'no-ollama' && (
          <div className="setup-wizard__choices">
            <p className="setup-wizard__status">
              Local AI engine not detected. IntentOS works best with Ollama
              installed.
            </p>
            <div className="setup-wizard__buttons">
              <button
                className="setup-wizard__btn--primary"
                onClick={() => window.open('https://ollama.com', '_blank')}
              >
                Download Ollama
              </button>
              <button
                className="setup-wizard__btn--secondary"
                onClick={onComplete}
              >
                Continue without local AI
              </button>
            </div>
          </div>
        )}

        {stage === 'timeout' && (
          <div className="setup-wizard__choices">
            <p className="setup-wizard__status">
              IntentOS backend is starting...
            </p>
            <div className="setup-wizard__buttons">
              <button
                className="setup-wizard__btn--primary"
                onClick={handleRetry}
              >
                Retry
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
