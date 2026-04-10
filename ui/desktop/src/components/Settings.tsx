import { useState, useEffect, useCallback } from 'react';
import { X, Shield, Cpu, HardDrive, FolderOpen, Key, Plus, Trash2, Check, Eye, EyeOff } from 'lucide-react';
import { getApiBaseUrl } from '../lib/platform';
import type { Settings as SettingsType } from '../types';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
  settings: SettingsType;
  onUpdate: (settings: Partial<SettingsType>) => void;
}

const privacyOptions: { value: SettingsType['privacyMode']; label: string; description: string }[] = [
  { value: 'local_only', label: 'Local Only', description: 'All processing stays on your machine' },
  { value: 'smart_routing', label: 'Smart Routing', description: 'Routes tasks based on complexity and privacy' },
  { value: 'performance', label: 'Performance', description: 'Prioritizes speed, may use cloud models' },
];

const providers = [
  { key: 'ANTHROPIC_API_KEY', label: 'Anthropic (Claude)', placeholder: 'sk-ant-...' },
  { key: 'OPENAI_API_KEY', label: 'OpenAI (GPT)', placeholder: 'sk-...' },
  { key: 'GOOGLE_API_KEY', label: 'Google (Gemini)', placeholder: 'AI...' },
];

export function Settings({ isOpen, onClose, settings, onUpdate }: SettingsProps) {
  const [storedKeys, setStoredKeys] = useState<string[]>([]);
  const [addingProvider, setAddingProvider] = useState<string | null>(null);
  const [newKeyValue, setNewKeyValue] = useState('');
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  // Load stored credential names on open
  useEffect(() => {
    if (!isOpen) return;
    (async () => {
      try {
        const base = getApiBaseUrl();
        const res = await fetch(`${base}/api/credentials`);
        const data = await res.json();
        if (data.credentials) {
          setStoredKeys(data.credentials);
        }
      } catch {
        // ignore
      }
    })();
  }, [isOpen]);

  const handleSaveKey = useCallback(async (providerKey: string) => {
    if (!newKeyValue.trim()) return;

    try {
      const base = getApiBaseUrl();
      const res = await fetch(`${base}/api/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: providerKey, value: newKeyValue.trim() }),
      });
      const data = await res.json();
      if (data.status === 'stored') {
        setStoredKeys((prev) => [...new Set([...prev, providerKey])]);
        setNewKeyValue('');
        setAddingProvider(null);
        setSaveStatus(`${providerKey} saved`);
        setTimeout(() => setSaveStatus(null), 2000);
      }
    } catch {
      setSaveStatus('Failed to save');
      setTimeout(() => setSaveStatus(null), 2000);
    }
  }, [newKeyValue]);

  const handleDeleteKey = useCallback(async (providerKey: string) => {
    try {
      const base = getApiBaseUrl();
      await fetch(`${base}/api/credentials/${providerKey}`, { method: 'DELETE' });
      setStoredKeys((prev) => prev.filter((k) => k !== providerKey));
      setSaveStatus(`${providerKey} removed`);
      setTimeout(() => setSaveStatus(null), 2000);
    } catch {
      // ignore
    }
  }, []);

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-modal__header">
          <h2>Settings</h2>
          <button className="settings-modal__close" onClick={onClose} aria-label="Close settings">
            <X size={20} />
          </button>
        </div>

        <div className="settings-modal__content">
          {/* API Keys */}
          <section className="settings-section">
            <h3><Key size={16} /> API Keys</h3>
            <p className="settings-field__hint">
              Add API keys for cloud providers. Keys are stored encrypted on your device.
            </p>

            <div className="settings-keys">
              {providers.map((provider) => {
                const isStored = storedKeys.includes(provider.key);
                const isAdding = addingProvider === provider.key;

                return (
                  <div key={provider.key} className="settings-key-row">
                    <div className="settings-key-row__header">
                      <span className="settings-key-row__label">{provider.label}</span>
                      <div className="settings-key-row__actions">
                        {isStored && (
                          <>
                            <span className="settings-key-row__badge">
                              <Check size={12} /> Configured
                            </span>
                            <button
                              className="settings-key-row__btn settings-key-row__btn--update"
                              onClick={() => {
                                setAddingProvider(isAdding ? null : provider.key);
                                setNewKeyValue('');
                              }}
                            >
                              {isAdding ? 'Cancel' : 'Update'}
                            </button>
                            <button
                              className="settings-key-row__btn settings-key-row__btn--delete"
                              onClick={() => handleDeleteKey(provider.key)}
                              title="Remove key"
                            >
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                        {!isStored && !isAdding && (
                          <button
                            className="settings-key-row__btn settings-key-row__btn--add"
                            onClick={() => {
                              setAddingProvider(provider.key);
                              setNewKeyValue('');
                            }}
                          >
                            <Plus size={14} /> Add Key
                          </button>
                        )}
                      </div>
                    </div>

                    {isAdding && (
                      <div className="settings-key-row__input-row">
                        <div className="settings-key-row__input-wrapper">
                          <input
                            type={showKey[provider.key] ? 'text' : 'password'}
                            className="settings-key-row__input"
                            placeholder={provider.placeholder}
                            value={newKeyValue}
                            onChange={(e) => setNewKeyValue(e.target.value)}
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveKey(provider.key);
                            }}
                          />
                          <button
                            className="settings-key-row__eye"
                            onClick={() => setShowKey((prev) => ({
                              ...prev,
                              [provider.key]: !prev[provider.key],
                            }))}
                          >
                            {showKey[provider.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        </div>
                        <button
                          className="settings-key-row__save"
                          onClick={() => handleSaveKey(provider.key)}
                          disabled={!newKeyValue.trim()}
                        >
                          Save
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {saveStatus && (
              <div className="settings-key-status">{saveStatus}</div>
            )}
          </section>

          {/* Privacy Mode */}
          <section className="settings-section">
            <h3><Shield size={16} /> Privacy Mode</h3>
            <div className="settings-section__options">
              {privacyOptions.map((opt) => (
                <label
                  key={opt.value}
                  className={`settings-radio ${settings.privacyMode === opt.value ? 'settings-radio--active' : ''}`}
                >
                  <input
                    type="radio"
                    name="privacyMode"
                    value={opt.value}
                    checked={settings.privacyMode === opt.value}
                    onChange={() => onUpdate({ privacyMode: opt.value })}
                  />
                  <div>
                    <strong>{opt.label}</strong>
                    <span>{opt.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* Models */}
          <section className="settings-section">
            <h3><Cpu size={16} /> Models</h3>
            <div className="settings-field">
              <label>Local Model</label>
              <span className="settings-field__value">{settings.localModel}</span>
            </div>
            <div className="settings-field">
              <label>Cloud Model</label>
              <span className="settings-field__value">{settings.cloudModel}</span>
            </div>
          </section>

          {/* Hardware */}
          <section className="settings-section">
            <h3><HardDrive size={16} /> Hardware</h3>
            <p className="settings-field__hint">Hardware profile will be detected at startup.</p>
          </section>

          {/* Workspace */}
          <section className="settings-section">
            <h3><FolderOpen size={16} /> Workspace</h3>
            <div className="settings-field">
              <label>Workspace Path</label>
              <span className="settings-field__value mono">{settings.workspacePath}</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
