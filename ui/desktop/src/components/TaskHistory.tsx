import { Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import type { Task } from '../types';

interface TaskHistoryProps {
  tasks: Task[];
  onSelect: (taskId: string) => void;
  selectedId?: string;
}

function statusIcon(status: Task['status']) {
  switch (status) {
    case 'success':
      return <CheckCircle2 size={14} className="status-icon status-icon--success" />;
    case 'error':
      return <XCircle size={14} className="status-icon status-icon--error" />;
    case 'executing':
      return <Loader2 size={14} className="status-icon status-icon--pending spin" />;
    default:
      return <Clock size={14} className="status-icon status-icon--pending" />;
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function TaskHistory({ tasks, onSelect, selectedId }: TaskHistoryProps) {
  return (
    <aside className="task-history">
      <h2 className="task-history__title">History</h2>
      {tasks.length === 0 ? (
        <p className="task-history__empty">No tasks yet</p>
      ) : (
        <ul className="task-history__list">
          {tasks.map((task) => (
            <li
              key={task.id}
              className={`task-history__item ${selectedId === task.id ? 'task-history__item--selected' : ''}`}
              onClick={() => onSelect(task.id)}
            >
              <div className="task-history__item-header">
                {statusIcon(task.status)}
                <span className="task-history__intent">{task.intent}</span>
              </div>
              <span className="task-history__time">{formatTime(task.createdAt)}</span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
