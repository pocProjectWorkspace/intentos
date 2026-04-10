import { MessageSquare, Plus, Trash2 } from 'lucide-react';
import type { Task, ChatSession } from '../types';

interface TaskHistoryProps {
  tasks: Task[];
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (taskId: string) => void;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  selectedId?: string;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return d.toLocaleDateString([], { weekday: 'short' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function TaskHistory({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}: TaskHistoryProps) {
  return (
    <aside className="task-history">
      <div className="task-history__header">
        <h2 className="task-history__title">Chats</h2>
        <button
          className="task-history__new-btn"
          onClick={onNewSession}
          aria-label="New chat"
          title="New chat"
        >
          <Plus size={16} />
        </button>
      </div>

      {sessions.length === 0 ? (
        <p className="task-history__empty">No conversations yet</p>
      ) : (
        <ul className="task-history__list">
          {sessions.map((session) => (
            <li
              key={session.id}
              className={`task-history__item ${activeSessionId === session.id ? 'task-history__item--selected' : ''}`}
              onClick={() => onSelectSession(session.id)}
            >
              <div className="task-history__item-header">
                <MessageSquare size={14} className="status-icon status-icon--success" />
                <span className="task-history__intent">{session.title}</span>
              </div>
              <div className="task-history__item-meta">
                <span className="task-history__time">{formatTime(session.updatedAt)}</span>
                <button
                  className="task-history__delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  aria-label="Delete chat"
                  title="Delete chat"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
