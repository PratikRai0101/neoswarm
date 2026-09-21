import React, { useCallback } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import ExtensionOutlinedIcon from '@mui/icons-material/ExtensionOutlined';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';
import {
  removeAppGrantRequest,
  resolveAppGrant,
  useAppGrantRequests,
} from '@/shared/appGrants';

/**
 * Floating approval cards for vibe-coded apps requesting tool access.
 * Deny-by-default: timeout or dismissal reads as deny server-side.
 */
const AppGrantIsland: React.FC = () => {
  const c = useClaudeTokens();
  const requests = useAppGrantRequests();

  const decide = useCallback((requestId: string, allow: boolean, remember: boolean) => {
    void resolveAppGrant(requestId, allow, remember);
  }, []);

  if (requests.length === 0) return null;

  return (
    <Box
      sx={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        zIndex: 1300,
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        width: 340,
        pointerEvents: 'none',
      }}
    >
      {requests.map((req) => (
        <Box
          key={req.request_id}
          sx={{
            pointerEvents: 'auto',
            borderRadius: '12px',
            bgcolor: 'rgba(15, 15, 15, 0.92)',
            backdropFilter: 'blur(16px)',
            border: `1px solid ${c.accent.primary}50`,
            boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
            p: 1.5,
            display: 'flex',
            flexDirection: 'column',
            gap: 0.75,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <ExtensionOutlinedIcon sx={{ fontSize: 15, color: c.accent.primary }} />
            <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.9)', flex: 1 }}>
              {req.app_name} wants to use {req.tool_label}
            </Typography>
            <IconButton
              size="small"
              onClick={() => removeAppGrantRequest(req.request_id)}
              sx={{ p: 0.3, color: 'rgba(255,255,255,0.4)', '&:hover': { color: 'rgba(255,255,255,0.8)' } }}
            >
              <CloseIcon sx={{ fontSize: 13 }} />
            </IconButton>
          </Box>

          {req.args_preview && (
            <Typography
              sx={{
                fontSize: '0.65rem',
                fontFamily: c.font.mono,
                color: 'rgba(255,255,255,0.5)',
                bgcolor: 'rgba(255,255,255,0.05)',
                borderRadius: '6px',
                px: 1,
                py: 0.5,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {req.args_preview}
            </Typography>
          )}

          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant="contained"
              onClick={() => decide(req.request_id, true, false)}
              sx={{ textTransform: 'none', fontSize: '0.68rem', fontWeight: 600, borderRadius: '6px', px: 1.25, py: 0.35, bgcolor: '#38bdf8', color: '#000', '&:hover': { bgcolor: '#0ea5e9' } }}
            >
              Allow once
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => decide(req.request_id, true, true)}
              sx={{ textTransform: 'none', fontSize: '0.68rem', borderRadius: '6px', px: 1.25, py: 0.35, color: '#38bdf8', borderColor: '#38bdf855' }}
            >
              Always allow
            </Button>
            <Button
              size="small"
              variant="text"
              onClick={() => decide(req.request_id, false, false)}
              sx={{ textTransform: 'none', fontSize: '0.68rem', borderRadius: '6px', px: 1, py: 0.35, color: 'rgba(255,255,255,0.6)' }}
            >
              Deny
            </Button>
            <Button
              size="small"
              variant="text"
              onClick={() => decide(req.request_id, false, true)}
              sx={{ textTransform: 'none', fontSize: '0.68rem', borderRadius: '6px', px: 1, py: 0.35, color: 'rgba(255,255,255,0.35)' }}
            >
              Never
            </Button>
          </Box>
        </Box>
      ))}
    </Box>
  );
};

export default AppGrantIsland;
