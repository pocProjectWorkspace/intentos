export const colors = {
  primary: '#2563EB',
  primaryHover: '#1D4ED8',
  primaryLight: '#DBEAFE',
  accent: '#10B981',
  accentHover: '#059669',
  error: '#EF4444',
  errorLight: '#FEE2E2',
  warning: '#F59E0B',
  warningLight: '#FEF3C7',

  bgDark: '#0F172A',
  bgDarkSecondary: '#1E293B',
  bgDarkTertiary: '#334155',
  textDark: '#F8FAFC',
  textDarkMuted: '#94A3B8',

  bgLight: '#FFFFFF',
  bgLightSecondary: '#F8FAFC',
  bgLightTertiary: '#E2E8F0',
  textLight: '#0F172A',
  textLightMuted: '#64748B',

  border: '#334155',
  borderLight: '#E2E8F0',
} as const;

export const typography = {
  fontHeading: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  fontMono: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
  fontBody: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
} as const;

export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  '2xl': '32px',
  '3xl': '48px',
} as const;

export const shadows = {
  sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
  md: '0 4px 6px rgba(0, 0, 0, 0.1)',
  lg: '0 10px 15px rgba(0, 0, 0, 0.15)',
  xl: '0 20px 25px rgba(0, 0, 0, 0.2)',
} as const;

export const radii = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  full: '9999px',
} as const;
