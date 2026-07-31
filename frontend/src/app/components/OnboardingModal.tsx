import React, { useState, useEffect } from 'react';
import { Box, Typography, Modal, Button, TextField, InputAdornment } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { useAppDispatch } from '@/shared/hooks';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';
import { API_BASE } from '@/shared/config';
import { trackEvent } from '@/shared/analytics';
import { openSettingsModal } from '@/shared/state/settingsSlice';

// Email validation: format check + typo correction for common domains.
// Real ownership verification is intentionally pushed downstream (mailing list /
// CRM system handles the confirm-subscription flow).
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const COMMON_DOMAIN_TYPOS: Record<string, string> = {
  'gmial.com': 'gmail.com',
  'gmai.com': 'gmail.com',
  'gnail.com': 'gmail.com',
  'gmaill.com': 'gmail.com',
  'gmail.co': 'gmail.com',
  'gmail.cm': 'gmail.com',
  'yahooo.com': 'yahoo.com',
  'yaho.com': 'yahoo.com',
  'yahoo.co': 'yahoo.com',
  'hotmial.com': 'hotmail.com',
  'hotmai.com': 'hotmail.com',
  'hotmail.co': 'hotmail.com',
  'outlok.com': 'outlook.com',
  'outloook.com': 'outlook.com',
  'iclould.com': 'icloud.com',
  'iclud.com': 'icloud.com',
  'protonmial.com': 'protonmail.com',
};

function getEmailSuggestion(email: string): string | null {
  const at = email.lastIndexOf('@');
  if (at < 0) return null;
  const domain = email.slice(at + 1).toLowerCase();
  const correction = COMMON_DOMAIN_TYPOS[domain];
  if (!correction) return null;
  return email.slice(0, at + 1) + correction;
}

function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email.trim());
}

const USE_CASES = [
  'Software Development',
  'Research & Analysis',
  'Content & Writing',
  'Data & Analytics',
  'Automation & Workflows',
  'Design & Creative',
  'Sales & Outreach',
  'Customer Support',
  'Marketing',
  'Education & Learning',
  'Personal Assistant',
  'Other',
];

const REFERRAL_SOURCES = [
  'Twitter / X',
  'LinkedIn',
  'YouTube',
  'TikTok',
  'Reddit',
  'Hacker News',
  'GitHub',
  'Friend / Word of mouth',
  'Search engine',
  'Blog / Article',
  'Other',
];

const OnboardingModal: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<'profile' | 'connect'>('profile');
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [emailBlurred, setEmailBlurred] = useState(false);
  const [useCases, setUseCases] = useState<string[]>([]);
  const [useCaseOther, setUseCaseOther] = useState<string>('');
  const [referralSource, setReferralSource] = useState<string>('');
  const [referralSourceOther, setReferralSourceOther] = useState<string>('');

  useEffect(() => {
    if (localStorage.getItem('neoswarm_onboarding_seen') === 'true') return;
    setOpen(true);
    trackEvent('onboarding.started', { step: 'profile' });
  }, []);

  const dismiss = async () => {
    localStorage.setItem('neoswarm_onboarding_seen', 'true');

    // Create a demo dashboard with a pre-populated example agent
    try {
      const createRes = await fetch(`${API_BASE}/dashboards/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Getting Started' }),
      });
      if (createRes.ok) {
        const dashboard = await createRes.json();
        if (dashboard?.id) {
          const seedRes = await fetch(`${API_BASE}/dashboards/${dashboard.id}/seed-demo`, { method: 'POST' });
          if (seedRes.ok) {
            trackEvent('onboarding.completed');
            localStorage.setItem('neoswarm_walkthrough_pending', 'true');
            setOpen(false);
            // Force full page load to ensure dashboard mounts fresh with walkthrough
            window.location.href = `${window.location.pathname}${window.location.search}#/dashboard/${dashboard.id}`;
            window.location.reload();
            return;
          }
        }
      }
    } catch (e) {
      console.warn('Demo dashboard creation failed:', e);
    }

    setOpen(false);
  };

  // Actually persist profile + advance to connect step.
  const submitProfile = async () => {
    try {
      const r = await fetch(`${API_BASE}/settings`);
      const currentSettings = await r.json();
      // If "Other" is selected, replace it with the user's custom text
      const resolvedUseCases = useCases.map((u) =>
        u === 'Other' && useCaseOther.trim() ? `Other: ${useCaseOther.trim()}` : u
      );
      const resolvedReferralSource =
        referralSource === 'Other' && referralSourceOther.trim()
          ? `Other: ${referralSourceOther.trim()}`
          : referralSource;
      await fetch(`${API_BASE}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...currentSettings,
          user_name: userName.trim() || null,
          user_email: userEmail.trim() || null,
          user_use_case: resolvedUseCases.length > 0 ? resolvedUseCases.join(', ') : null,
          user_referral_source: resolvedReferralSource || null,
        }),
      });
    } catch {}
    trackEvent('onboarding.profile_submitted');
    setStep('connect');
    trackEvent('onboarding.connect_started');
  };

  // Whether all required profile fields are filled in.
  const isProfileComplete = (() => {
    const trimmedName = userName.trim();
    const trimmedEmail = userEmail.trim();
    if (!trimmedName) return false;
    if (!trimmedEmail || !isValidEmail(trimmedEmail)) return false;
    if (useCases.length === 0) return false;
    if (useCases.includes('Other') && !useCaseOther.trim()) return false;
    if (!referralSource) return false;
    if (referralSource === 'Other' && !referralSourceOther.trim()) return false;
    return true;
  })();

  // Continue: gate on full profile completion, then submit.
  const handleProfileContinue = async () => {
    const trimmed = userEmail.trim();
    // Invalid format with non-empty value — refuse and force error state.
    if (trimmed && !isValidEmail(trimmed)) {
      setEmailBlurred(true);
      trackEvent('onboarding.email_invalid_blocked', { value_length: trimmed.length });
      return;
    }
    if (!isProfileComplete) return;
    submitProfile();
  };

  const handleApplySuggestion = (suggested: string) => {
    setUserEmail(suggested);
    trackEvent('onboarding.email_suggestion_applied');
  };

  const handleUseOllama = () => {
    trackEvent('onboarding.provider_selected', { provider: 'ollama' });
    dismiss();
  };

  const handleApiKey = () => {
    trackEvent('onboarding.api_key_chosen');
    localStorage.setItem('neoswarm_onboarding_seen', 'true');
    setOpen(false);
    dispatch(openSettingsModal('models'));
  };
  const handleProfileSkip = () => {
    trackEvent('onboarding.profile_skipped');
    setStep('connect');
  };
  const handleSkip = () => {
    trackEvent('onboarding.connect_skipped');
    dismiss();
  };

  if (!open) return null;

  return (
    <Modal open={open} onClose={step === 'connect' ? handleSkip : undefined} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Box sx={{
        width: 480, maxWidth: '90vw', bgcolor: c.bg.surface, borderRadius: `${c.radius.xl}px`,
        border: `1px solid ${c.border.subtle}`, p: 3.5, outline: 'none',
        boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
      }}>
        <Typography sx={{ fontSize: '1.3rem', fontWeight: 700, color: c.text.primary, mb: 0.5, textAlign: 'center' }}>
          Welcome to NeoSwarm
        </Typography>

        {step === 'profile' ? (
          <>
            <Typography sx={{ fontSize: '0.78rem', color: c.text.muted, mb: 2.5, textAlign: 'center' }}>
              Tell us a bit about yourself (optional)
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mb: 2.5 }}>
              <TextField
                placeholder="Your name"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                size="small"
                fullWidth
                sx={{
                  '& .MuiOutlinedInput-root': {
                    fontSize: '0.82rem',
                    color: c.text.primary,
                    borderRadius: `${c.radius.md}px`,
                    '& fieldset': { borderColor: c.border.subtle },
                    '&:hover fieldset': { borderColor: c.border.medium },
                    '&.Mui-focused fieldset': { borderColor: c.accent.primary },
                  },
                  '& .MuiOutlinedInput-input::placeholder': { color: c.text.ghost, opacity: 1 },
                }}
              />
              {(() => {
                const trimmed = userEmail.trim();
                const valid = trimmed.length > 0 && isValidEmail(trimmed);
                const showError = emailBlurred && trimmed.length > 0 && !valid;
                const suggestion = valid ? getEmailSuggestion(trimmed) : null;
                return (
                  <Box>
                    <TextField
                      placeholder="Email address"
                      type="email"
                      value={userEmail}
                      onChange={(e) => setUserEmail(e.target.value)}
                      onBlur={() => setEmailBlurred(true)}
                      error={showError}
                      size="small"
                      fullWidth
                      InputProps={{
                        endAdornment: valid ? (
                          <InputAdornment position="end">
                            <CheckCircleIcon sx={{ fontSize: 16, color: c.status.success }} />
                          </InputAdornment>
                        ) : undefined,
                      }}
                      sx={{
                        '& .MuiOutlinedInput-root': {
                          fontSize: '0.82rem',
                          color: c.text.primary,
                          borderRadius: `${c.radius.md}px`,
                          '& fieldset': { borderColor: showError ? c.status.error : c.border.subtle },
                          '&:hover fieldset': { borderColor: showError ? c.status.error : c.border.medium },
                          '&.Mui-focused fieldset': { borderColor: showError ? c.status.error : c.accent.primary },
                        },
                        '& .MuiOutlinedInput-input::placeholder': { color: c.text.ghost, opacity: 1 },
                      }}
                    />
                    {showError && (
                      <Typography sx={{ fontSize: '0.68rem', color: c.status.error, mt: 0.4, ml: 0.5 }}>
                        That doesn't look like a valid email address
                      </Typography>
                    )}
                    {suggestion && (
                      <Typography sx={{ fontSize: '0.68rem', color: c.text.muted, mt: 0.4, ml: 0.5 }}>
                        Did you mean{' '}
                        <Box
                          component="span"
                          onClick={() => handleApplySuggestion(suggestion)}
                          sx={{
                            color: c.accent.primary,
                            fontWeight: 600,
                            cursor: 'pointer',
                            '&:hover': { textDecoration: 'underline' },
                          }}
                        >
                          {suggestion}
                        </Box>
                        ?
                      </Typography>
                    )}
                  </Box>
                );
              })()}

              <Typography sx={{ fontSize: '0.65rem', fontWeight: 600, color: c.text.tertiary, textTransform: 'uppercase', letterSpacing: '0.08em', mt: 0.5 }}>
                What will you use NeoSwarm for?
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
                {USE_CASES.map((uc) => (
                  <Box
                    key={uc}
                    onClick={() => setUseCases(prev => prev.includes(uc) ? prev.filter(u => u !== uc) : [...prev, uc])}
                    sx={{
                      px: 1.5, py: 0.6,
                      borderRadius: `${c.radius.md}px`,
                      border: `1px solid ${useCases.includes(uc) ? c.accent.primary : c.border.subtle}`,
                      bgcolor: useCases.includes(uc) ? `${c.accent.primary}15` : 'transparent',
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                      '&:hover': { borderColor: c.border.medium },
                    }}
                  >
                    <Typography sx={{ fontSize: '0.72rem', color: useCases.includes(uc) ? c.accent.primary : c.text.secondary }}>
                      {uc}
                    </Typography>
                  </Box>
                ))}
              </Box>
              {useCases.includes('Other') && (
                <TextField
                  placeholder="Tell us what else..."
                  value={useCaseOther}
                  onChange={(e) => setUseCaseOther(e.target.value)}
                  size="small"
                  fullWidth
                  sx={{
                    mt: 0.5,
                    '& .MuiOutlinedInput-root': {
                      fontSize: '0.82rem',
                      color: c.text.primary,
                      borderRadius: `${c.radius.md}px`,
                      '& fieldset': { borderColor: c.border.subtle },
                      '&:hover fieldset': { borderColor: c.border.medium },
                      '&.Mui-focused fieldset': { borderColor: c.accent.primary },
                    },
                    '& .MuiOutlinedInput-input::placeholder': { color: c.text.ghost, opacity: 1 },
                  }}
                />
              )}

              <Typography sx={{ fontSize: '0.65rem', fontWeight: 600, color: c.text.tertiary, textTransform: 'uppercase', letterSpacing: '0.08em', mt: 0.5 }}>
                How did you hear about NeoSwarm?
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
                {REFERRAL_SOURCES.map((src) => (
                  <Box
                    key={src}
                    onClick={() => setReferralSource(prev => prev === src ? '' : src)}
                    sx={{
                      px: 1.5, py: 0.6,
                      borderRadius: `${c.radius.md}px`,
                      border: `1px solid ${referralSource === src ? c.accent.primary : c.border.subtle}`,
                      bgcolor: referralSource === src ? `${c.accent.primary}15` : 'transparent',
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                      '&:hover': { borderColor: c.border.medium },
                    }}
                  >
                    <Typography sx={{ fontSize: '0.72rem', color: referralSource === src ? c.accent.primary : c.text.secondary }}>
                      {src}
                    </Typography>
                  </Box>
                ))}
              </Box>
              {referralSource === 'Other' && (
                <TextField
                  placeholder="Where did you hear about us?"
                  value={referralSourceOther}
                  onChange={(e) => setReferralSourceOther(e.target.value)}
                  size="small"
                  fullWidth
                  sx={{
                    mt: 0.5,
                    '& .MuiOutlinedInput-root': {
                      fontSize: '0.82rem',
                      color: c.text.primary,
                      borderRadius: `${c.radius.md}px`,
                      '& fieldset': { borderColor: c.border.subtle },
                      '&:hover fieldset': { borderColor: c.border.medium },
                      '&.Mui-focused fieldset': { borderColor: c.accent.primary },
                    },
                    '& .MuiOutlinedInput-input::placeholder': { color: c.text.ghost, opacity: 1 },
                  }}
                />
              )}
            </Box>

            <Button
              onClick={handleProfileContinue}
              fullWidth
              disabled={!isProfileComplete}
              sx={{
                textTransform: 'none', fontSize: '0.82rem', fontWeight: 600,
                bgcolor: c.accent.primary, color: '#fff',
                borderRadius: `${c.radius.md}px`, py: 1,
                '&:hover': { bgcolor: c.accent.hover },
                '&.Mui-disabled': { bgcolor: c.accent.primary, color: '#fff', opacity: 0.4 },
                mb: 1,
              }}
            >
              Continue
            </Button>
            <Button
              onClick={handleProfileSkip}
              fullWidth
              sx={{ textTransform: 'none', fontSize: '0.72rem', color: c.text.ghost, '&:hover': { bgcolor: 'transparent', color: c.text.muted } }}
            >
              Skip profile
            </Button>
          </>
        ) : (
          <>
            <Typography sx={{ fontSize: '0.78rem', color: c.text.muted, mb: 3, textAlign: 'center' }}>
              Connect an AI model to get started
            </Typography>

            <Typography sx={{ fontSize: '0.65rem', fontWeight: 600, color: c.text.tertiary, textTransform: 'uppercase', letterSpacing: '0.08em', mb: 1 }}>
              Run locally
            </Typography>
            <Box
              onClick={handleUseOllama}
              sx={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                p: 1.5, mb: 2.5, borderRadius: `${c.radius.md}px`, border: `1px solid ${c.border.subtle}`,
                cursor: 'pointer',
                '&:hover': { borderColor: c.border.medium, bgcolor: `${c.accent.primary}05` },
              }}
            >
              <Box>
                <Typography sx={{ fontSize: '0.82rem', fontWeight: 600, color: c.text.primary }}>Ollama</Typography>
                <Typography sx={{ fontSize: '0.65rem', color: c.text.muted }}>Private, local models with no API key</Typography>
              </Box>
              <Typography sx={{ fontSize: '0.68rem', color: c.text.tertiary }}>Use local →</Typography>
            </Box>

            <Typography sx={{ fontSize: '0.65rem', fontWeight: 600, color: c.text.tertiary, textTransform: 'uppercase', letterSpacing: '0.08em', mb: 1 }}>
              Or connect a cloud API
            </Typography>
            <Box
              onClick={handleApiKey}
              sx={{
                p: 1.5, borderRadius: `${c.radius.md}px`, border: `1px solid ${c.border.subtle}`,
                cursor: 'pointer', mb: 2.5,
                '&:hover': { borderColor: c.border.medium, bgcolor: `${c.accent.primary}05` },
              }}
            >
              <Typography sx={{ fontSize: '0.78rem', color: c.text.primary }}>
                I have an API key
              </Typography>
              <Typography sx={{ fontSize: '0.65rem', color: c.text.muted }}>
                Go to Settings &rarr; Models to enter your key
              </Typography>
            </Box>

            {/* Skip */}
            <Button
              onClick={handleSkip}
              fullWidth
              sx={{ textTransform: 'none', fontSize: '0.72rem', color: c.text.ghost, '&:hover': { bgcolor: 'transparent', color: c.text.muted } }}
            >
              Skip for now
            </Button>
          </>
        )}
      </Box>
    </Modal>
  );
};

export default OnboardingModal;
