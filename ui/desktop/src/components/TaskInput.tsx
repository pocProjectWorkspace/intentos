import { useState, useCallback, useRef, type KeyboardEvent } from 'react';
import { ArrowUp, Loader2, Mic, MicOff, Paperclip, X, Square } from 'lucide-react';

interface AttachedFile {
  fileId: string;
  name: string;
  sizeBytes: number;
}

interface TaskInputProps {
  onSubmit: (input: string, fileId?: string) => void;
  isLoading: boolean;
  onStop?: () => void;
}

const ALLOWED_EXTENSIONS = [
  '.pdf', '.txt', '.csv', '.md', '.json',
  '.docx', '.xlsx', '.pptx', '.doc',
  '.png', '.jpg', '.jpeg', '.gif', '.webp',
];

const MAX_SIZE_MB = 50;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function TaskInput({ onSubmit, isLoading, onStop }: TaskInputProps) {
  const [value, setValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [attachedFile, setAttachedFile] = useState<AttachedFile | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSubmit(trimmed, attachedFile?.fileId);
    setValue('');
    setAttachedFile(null);
  }, [value, isLoading, onSubmit, attachedFile]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset file input so same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = '';

    setUploadError(null);

    // Validate extension
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setUploadError(`Unsupported file type: ${ext}`);
      return;
    }

    // Validate size
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setUploadError(`File too large (max ${MAX_SIZE_MB} MB)`);
      return;
    }

    setIsUploading(true);

    try {
      // Read file as base64
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = reader.result as string;
          // Strip the data:...;base64, prefix
          const b64 = result.split(',')[1];
          resolve(b64);
        };
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
      });

      // Upload to API
      const { getApiBaseUrl } = await import('../lib/platform');
      const base = getApiBaseUrl();
      const res = await fetch(`${base}/api/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: file.name,
          mime: file.type || 'application/octet-stream',
          data: base64,
        }),
      });

      const data = await res.json();

      if (!res.ok || data.error) {
        setUploadError(data.error || 'Upload failed');
        return;
      }

      setAttachedFile({
        fileId: data.file_id,
        name: data.name,
        sizeBytes: data.size_bytes,
      });

      // Auto-fill prompt if empty
      if (!value.trim()) {
        const isImage = file.type.startsWith('image/');
        setValue(isImage ? 'Describe this image' : 'Summarize this document');
      }
    } catch {
      setUploadError('Upload failed — is the backend running?');
    } finally {
      setIsUploading(false);
    }
  }, [value]);

  const handleRemoveFile = useCallback(() => {
    setAttachedFile(null);
    setUploadError(null);
  }, []);

  const handleVoiceInput = useCallback(async () => {
    if (isListening || isLoading) return;

    setIsListening(true);
    setVoiceError(null);

    try {
      const { getApiBaseUrl } = await import('../lib/platform');
      const base = getApiBaseUrl();
      const response = await fetch(`${base}/api/voice/listen`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration: 5 }),
      });

      if (!response.ok) throw new Error('Voice input unavailable');

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
      {/* Attached file chip */}
      {attachedFile && (
        <div className="task-input__file-chip">
          <Paperclip size={12} />
          <span className="task-input__file-name">{attachedFile.name}</span>
          <span className="task-input__file-size">({formatSize(attachedFile.sizeBytes)})</span>
          <button
            className="task-input__file-remove"
            onClick={handleRemoveFile}
            aria-label="Remove file"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <div className="task-input__wrapper">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        {/* Attach button */}
        <button
          className="task-input__attach"
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading || isUploading}
          aria-label="Attach file"
          title="Attach a document or image"
        >
          {isUploading ? (
            <Loader2 size={18} className="spin" />
          ) : (
            <Paperclip size={18} />
          )}
        </button>

        <input
          type="text"
          className="task-input__field"
          placeholder={
            isListening ? 'Listening...'
            : attachedFile ? `Ask about ${attachedFile.name}...`
            : 'Tell IntentOS what to do...'
          }
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
        {isLoading ? (
          <button
            className="task-input__stop"
            onClick={onStop}
            aria-label="Stop task"
            title="Stop generation"
          >
            <Square size={14} />
          </button>
        ) : (
          <button
            className="task-input__submit"
            onClick={handleSubmit}
            disabled={!value.trim()}
            aria-label="Submit task"
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>

      {(voiceError || uploadError) && (
        <div className="task-input__voice-error">
          {uploadError || voiceError}
        </div>
      )}
    </div>
  );
}
