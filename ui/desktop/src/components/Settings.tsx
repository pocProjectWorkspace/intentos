import { X, Shield, Cpu, HardDrive, FolderOpen } from 'lucide-react';
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

export function Settings({ isOpen, onClose, settings, onUpdate }: SettingsProps) {
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

          <section className="settings-section">
            <h3><HardDrive size={16} /> Hardware</h3>
            <p className="settings-field__hint">Hardware profile will be detected at startup.</p>
          </section>

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
