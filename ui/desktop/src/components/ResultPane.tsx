import { CheckCircle2, XCircle, Clock, Loader2, Zap } from 'lucide-react';
import type { Task, Subtask } from '../types';

interface ResultPaneProps {
  task: Task | null;
}

function subtaskStatusIcon(status: Subtask['status']) {
  switch (status) {
    case 'success':
      return <CheckCircle2 size={14} className="status-icon status-icon--success" />;
    case 'error':
      return <XCircle size={14} className="status-icon status-icon--error" />;
    case 'running':
      return <Loader2 size={14} className="status-icon status-icon--pending spin" />;
    case 'skipped':
      return <Clock size={14} className="status-icon status-icon--muted" />;
    default:
      return <Clock size={14} className="status-icon status-icon--pending" />;
  }
}

function WelcomeMessage() {
  return (
    <div className="result-pane__welcome">
      <Zap size={48} className="result-pane__welcome-icon" />
      <h2>Welcome to IntentOS</h2>
      <p>Type a command below to get started. Describe what you want to do in natural language.</p>
    </div>
  );
}

export function ResultPane({ task }: ResultPaneProps) {
  if (!task) return <WelcomeMessage />;

  return (
    <div className="result-pane">
      <div className="result-pane__header">
        <h2 className="result-pane__intent">{task.intent}</h2>
        <span className={`result-pane__status result-pane__status--${task.status}`}>
          {task.status}
        </span>
      </div>

      <p className="result-pane__raw-input">{task.rawInput}</p>

      {task.durationMs !== undefined && (
        <p className="result-pane__duration">Completed in {task.durationMs}ms</p>
      )}

      {task.subtasks.length > 0 && (
        <div className="result-pane__subtasks">
          <h3>Subtasks</h3>
          <ul className="result-pane__subtask-list">
            {task.subtasks.map((st) => (
              <li key={st.id} className="result-pane__subtask-item">
                {subtaskStatusIcon(st.status)}
                <span className="result-pane__subtask-agent">{st.agent}</span>
                <span className="result-pane__subtask-action">{st.action}</span>
                {st.result && (
                  <pre className="result-pane__subtask-result">
                    {typeof st.result === 'string' ? st.result : JSON.stringify(st.result, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {task.result && (
        <div className="result-pane__result">
          <h3>Result</h3>
          <pre className="result-pane__result-content">
            {typeof task.result === 'string' ? task.result : JSON.stringify(task.result, null, 2)}
          </pre>
        </div>
      )}

      {task.error && (
        <div className="result-pane__error">
          <h3>Error</h3>
          <pre className="result-pane__error-content">{task.error}</pre>
        </div>
      )}
    </div>
  );
}
