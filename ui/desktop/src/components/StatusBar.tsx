import { Wifi, WifiOff, Shield, Zap } from 'lucide-react';
import { useApiStatus } from '../hooks/useIntentOS';
import type { Settings } from '../types';

interface StatusBarProps {
  settings: Settings;
  tokensUsed: number;
  tokenBudget: number;
}

const privacyLabels: Record<Settings['privacyMode'], string> = {
  local_only: 'Local Only',
  smart_routing: 'Smart Routing',
  performance: 'Performance',
};

export function StatusBar({ settings, tokensUsed, tokenBudget }: StatusBarProps) {
  const connected = useApiStatus();

  return (
    <footer className="status-bar">
      <div className="status-bar__left">
        <span className="status-bar__item">
          <Zap size={12} />
          {settings.localModel}
        </span>
        <span className="status-bar__item">
          <Shield size={12} />
          {privacyLabels[settings.privacyMode]}
        </span>
      </div>
      <div className="status-bar__right">
        <span className="status-bar__item">
          {tokensUsed.toLocaleString()} / {tokenBudget.toLocaleString()} tokens
        </span>
        <span className={`status-bar__item status-bar__connection ${connected ? 'status-bar__connection--on' : 'status-bar__connection--off'}`}>
          {connected ? <Wifi size={12} /> : <WifiOff size={12} />}
          {connected ? 'Connected' : 'Offline \u2014 using mock data'}
        </span>
      </div>
    </footer>
  );
}
