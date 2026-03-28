import { useState, useCallback, type KeyboardEvent } from 'react';
import { ArrowUp, Loader2, Mic, MicOff } from 'lucide-react';

interface TaskInputProps {
  onSubmit: (input: string) => void;
  isLoading: boolean;
}

export function TaskInput({ onSubmit, isLoading }: TaskInputProps) {
  const [value, setValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed);
    setValue('');
  }, [value, isLoading, onSubmit]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleVoiceInput = useCallback(async () => {
    if (isListening || isLoading) return;

    setIsListening(true);
    setVoiceError(null);

    try {
      const response = await fetch('/api/voice/listen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: 5 }),
      });

      if (!response.ok) {
        throw new Error('Voice input unavailable');
      }

      const data = await response.json();
      if (data.text) {
        setValue(data.text);
      } else {
        setVoiceError('Could not understand audio. Try again.');
      }
    } catch {
      setVoiceError('Voice input not available on this server.');
    } finally {
      setIsListening(false);
    }
  }, [isListening, isLoading]);

  return (
    <div className="task-input">
      <div className="task-input__wrapper">
        <input
          type="text"
          className="task-input__field"
          placeholder={isListening ? 'Listening...' : 'Tell IntentOS what to do...'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading || isListening}
          autoFocus
        />
        <button
          className="task-input__mic"
          onClick={handleVoiceInput}
          disabled={isLoading || isListening}
          aria-label={isListening ? 'Listening...' : 'Voice input'}
          title={isListening ? 'Listening...' : 'Speak a task'}
        >
          {isListening ? (
            <Mic size={18} className="pulse" />
          ) : (
            <MicOff size={18} />
          )}
        </button>
        <button
          className="task-input__submit"
          onClick={handleSubmit}
          disabled={!value.trim() || isLoading}
          aria-label="Submit task"
        >
          {isLoading ? (
            <Loader2 size={18} className="spin" />
          ) : (
            <ArrowUp size={18} />
          )}
        </button>
      </div>
      {voiceError && (
        <div className="task-input__voice-error">{voiceError}</div>
      )}
    </div>
  );
}
