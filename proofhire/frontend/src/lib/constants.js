// Literal strings from Section 5.1 of the guidebook. Do not rename.

export const STORAGE_KEYS = {
  token: 'ph_token',
  user: 'ph_user',
  ownerTokens: 'ph_owner_tokens',
  theme: 'ph_theme',
};

export const DISCLAIMER = 'ProofHire gives a risk estimate, not a verification of the employer.';
export const METRICS_BADGE = 'Metrics are from a synthetic benchmark.';

export const DEFAULT_THRESHOLDS = { low: 0.35, high: 0.7 };

// Hex values mirror the CSS tokens in styles/tokens.css (Recharts needs real colour strings).
export const CHART_COLORS = {
  navy: '#0B1F3A',
  teal: '#0F9D8F',
  low: '#16A34A',
  medium: '#D97706',
  high: '#DC2626',
};

export const RISK_LEVELS = ['low', 'medium', 'high'];

export const RISK_LABELS = {
  low: 'Low risk',
  medium: 'Medium risk',
  high: 'High risk',
};

export const WORK_MODE_OPTIONS = [
  { value: 'onsite', label: 'On-site' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
];

export const EMPLOYMENT_TYPE_OPTIONS = [
  { value: 'internship', label: 'Internship' },
  { value: 'full_time', label: 'Full-time' },
  { value: 'part_time', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
];

export const PAY_PERIOD_OPTIONS = [
  { value: 'month', label: 'Per month' },
  { value: 'year', label: 'Per year' },
  { value: 'one_time', label: 'One-time' },
];

export const APPLICATION_CHANNEL_OPTIONS = [
  { value: 'unknown', label: 'Not stated' },
  { value: 'email', label: 'Email' },
  { value: 'website_form', label: 'Website form' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'phone', label: 'Phone' },
  { value: 'linkedin_dm', label: 'LinkedIn message' },
];

export const INTERVIEW_MODE_OPTIONS = [
  { value: 'none', label: 'No interview mentioned' },
  { value: 'video_call', label: 'Video call' },
  { value: 'in_person', label: 'In person' },
  { value: 'phone_call', label: 'Phone call' },
  { value: 'chat_only', label: 'Chat only' },
];

export const REPORT_TYPE_OPTIONS = [
  { value: 'advance_fee', label: 'Asks for money upfront' },
  { value: 'impersonation', label: 'Impersonates a company or person' },
  { value: 'personal_data_request', label: 'Asks for sensitive personal data' },
  { value: 'fake_company', label: 'Company appears fake' },
  { value: 'harassment', label: 'Harassment' },
  { value: 'other', label: 'Other' },
];

export const SIGNAL_TYPE_LABELS = {
  email: 'Email',
  email_domain: 'Email domain',
  phone: 'Phone',
  website_domain: 'Website domain',
  company_name: 'Company name',
};

export const REPORT_STATUS_LABELS = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
};

export function labelFor(options, value) {
  const found = options.find((o) => o.value === value);
  return found ? found.label : value ?? '—';
}
