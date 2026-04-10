import { XCircle, Loader2, Zap } from 'lucide-react';
import { useEffect, useRef } from 'react';
import Markdown from 'react-markdown';
import type { Task, ChatMessage } from '../types';
import type { StreamState } from '../hooks/useIntentOS';

interface ResultPaneProps {
  task: Task | null;
  stream: StreamState;
  chatMessages: ChatMessage[];
  onSuggestionClick?: (text: string) => void;
}

function WelcomeMessage() {
  return (
    <div className="result-pane__welcome">
      <Zap size={48} className="result-pane__welcome-icon" />
      <h2>Welcome to IntentOS</h2>
      <p>Type a command below to get started. Describe what you want to do in natural language.</p>
      <div className="result-pane__examples">
        <p className="result-pane__examples-label">Try:</p>
        <ul>
          <li>"List files in my Documents folder"</li>
          <li>"What's my disk usage?"</li>
          <li>"Find all PDFs on my Desktop"</li>
          <li>"Create a file called notes.txt"</li>
        </ul>
      </div>
    </div>
  );
}

function formatCost(costUsd?: number): string {
  if (!costUsd || costUsd === 0) return 'free (local)';
  return `$${costUsd.toFixed(4)}`;
}

function formatDuration(ms?: number): string {
  if (!ms) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function FormattedReport({ text }: { text: string }) {
  return (
    <div className="result-pane__markdown">
      <Markdown>{text}</Markdown>
    </div>
  );
}

export function ResultPane({ task, stream, chatMessages, onSuggestionClick }: ResultPaneProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive or stream updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages.length, stream.streamedText, stream.statusMessage]);

  const hasMessages = chatMessages.length > 0 || stream.isStreaming;

  if (!hasMessages && !task) {
    return <WelcomeMessage />;
  }

  return (
    <div className="result-pane result-pane--chat">
      {/* Render full conversation history */}
      {chatMessages.map((msg) => (
        <div key={msg.id} className={`result-pane__message result-pane__message--${msg.role === 'user' ? 'user' : 'assistant'}`}>
          {msg.role === 'user' ? (
            <>
              <p>{msg.content}</p>
              {msg.fileName && (
                <span className="result-pane__file-badge">{msg.fileName}</span>
              )}
            </>
          ) : (
            <>
              <FormattedReport text={msg.content} />
              {(msg.durationMs || msg.costUsd) ? (
                <div className="result-pane__meta">
                  {msg.durationMs ? <span>{formatDuration(msg.durationMs)}</span> : null}
                  <span>{formatCost(msg.costUsd)}</span>
                </div>
              ) : null}
            </>
          )}
        </div>
      ))}

      {/* Streaming state — shown while actively processing */}
      {stream.isStreaming && (
        <>
          {stream.statusMessage && !stream.streamedText && (
            <div className="result-pane__message result-pane__message--assistant">
              <div className="result-pane__status-step">
                <Loader2 size={14} className="spin" />
                <span>{stream.statusMessage}</span>
              </div>
            </div>
          )}
          {stream.streamedText && (
            <div className="result-pane__message result-pane__message--assistant">
              <FormattedReport text={stream.streamedText} />
              <span className="result-pane__cursor" />
            </div>
          )}
        </>
      )}

      {/* Follow-up suggestions (only on the latest completed task) */}
      {!stream.isStreaming && task?.suggestions && task.suggestions.length > 0 && (
        <div className="result-pane__suggestions">
          {task.suggestions.map((suggestion, i) => (
            <button
              key={i}
              className="result-pane__suggestion-chip"
              onClick={() => onSuggestionClick?.(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} />
    </div>
  );
}
