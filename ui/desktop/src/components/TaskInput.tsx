import { useState, useCallback, type KeyboardEvent } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';

interface TaskInputProps {
  onSubmit: (input: string) => void;
  isLoading: boolean;
}

export function TaskInput({ onSubmit, isLoading }: TaskInputProps) {
  const [value, setValue] = useState('');

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

  return (
    <div className="task-input">
      <div className="task-input__wrapper">
        <input
          type="text"
          className="task-input__field"
          placeholder="Tell IntentOS what to do..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          autoFocus
        />
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
    </div>
  );
}
