import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import ClearAllOutlinedIcon from '@mui/icons-material/ClearAllOutlined';
import CloseIcon from '@mui/icons-material/Close';
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import StopCircleOutlinedIcon from '@mui/icons-material/StopCircleOutlined';
import TerminalOutlinedIcon from '@mui/icons-material/TerminalOutlined';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import { WS_BASE } from '@/shared/config';
import {
  appendTerminalOutput,
  clearTerminalError,
  clearTerminalOutput,
  createTerminal,
  deleteTerminal,
  fetchTerminals,
  setActiveTerminal,
  setTerminalError,
  startTerminal,
  Terminal,
  updateTerminal,
} from '@/shared/state/terminalsSlice';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

const TERMINAL_FONT_WIDTH = 8;
const TERMINAL_LINE_HEIGHT = 18;

const Terminals: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const items = useAppSelector((state) => state.terminals.items);
  const outputs = useAppSelector((state) => state.terminals.outputs);
  const activeId = useAppSelector((state) => state.terminals.activeId);
  const loading = useAppSelector((state) => state.terminals.loading);
  const saving = useAppSelector((state) => state.terminals.saving);
  const error = useAppSelector((state) => state.terminals.error);
  const defaultFolder = useAppSelector((state) => state.settings.data.default_folder);
  const terminals = useMemo(
    () => Object.values(items).sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [items],
  );
  const active = activeId ? items[activeId] : null;
  const [cwd, setCwd] = useState(defaultFolder || '');
  const [input, setInput] = useState('');
  const socketRef = useRef<WebSocket | null>(null);
  const outputRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    dispatch(fetchTerminals());
  }, [dispatch]);

  useEffect(() => {
    if (defaultFolder && !cwd) setCwd(defaultFolder);
  }, [cwd, defaultFolder]);

  useEffect(() => {
    setInput('');
  }, [activeId]);

  const sendResize = useCallback(() => {
    const socket = socketRef.current;
    const body = outputRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !body) return;
    socket.send(JSON.stringify({
      type: 'resize',
      cols: Math.max(40, Math.floor(body.clientWidth / TERMINAL_FONT_WIDTH)),
      rows: Math.max(10, Math.floor(body.clientHeight / TERMINAL_LINE_HEIGHT)),
    }));
  }, []);

  useEffect(() => {
    const previous = socketRef.current;
    previous?.close();
    socketRef.current = null;
    if (!active || active.status !== 'running') return undefined;

    const socket = new WebSocket(`${WS_BASE}/terminals/${active.id}`);
    socketRef.current = socket;
    socket.onopen = sendResize;
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as { event?: string; data?: any };
        if (message.event === 'terminal:output' && typeof message.data === 'string') {
          dispatch(appendTerminalOutput({ id: active.id, output: message.data }));
        } else if (message.event === 'terminal:state' && message.data?.id) {
          dispatch(updateTerminal(message.data as Terminal));
        } else if (message.event === 'terminal:exit') {
          dispatch(updateTerminal({
            ...active,
            status: message.data?.status || 'exited',
            pid: null,
            exit_code: message.data?.exit_code ?? null,
          }));
        } else if (message.event === 'terminal:error') {
          dispatch(setTerminalError(message.data?.error || 'Terminal error.'));
        }
      } catch {
        dispatch(setTerminalError('Received invalid terminal data.'));
      }
    };
    socket.onerror = () => dispatch(setTerminalError('Terminal connection failed.'));
    return () => {
      socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [active?.id, active?.status, dispatch, sendResize]);

  useEffect(() => {
    const body = outputRef.current;
    if (!body) return undefined;
    body.scrollTop = body.scrollHeight;
    const observer = new ResizeObserver(sendResize);
    observer.observe(body);
    return () => observer.disconnect();
  }, [active?.id, sendResize]);

  useEffect(() => {
    const body = outputRef.current;
    if (body) body.scrollTop = body.scrollHeight;
  }, [active?.id, active && outputs[active.id]]);

  const send = (message: Record<string, unknown>) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      dispatch(setTerminalError('Terminal is not connected.'));
      return false;
    }
    socketRef.current.send(JSON.stringify(message));
    return true;
  };

  const handleCreate = async () => {
    const result = await dispatch(createTerminal({ cwd: cwd.trim() || undefined }));
    if (createTerminal.fulfilled.match(result)) setInput('');
  };

  const handleDelete = async (terminal: Terminal) => {
    if (!window.confirm(`Close terminal in ${terminal.cwd}?`)) return;
    await dispatch(deleteTerminal(terminal.id));
  };

  const handleStart = async (terminal: Terminal) => {
    await dispatch(startTerminal(terminal.id));
  };

  const handleSubmit = () => {
    if (!input) return;
    if (send({ type: 'input', data: `${input}\n` })) setInput('');
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1400, mx: 'auto', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <TerminalOutlinedIcon />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>Terminal</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>Run interactive local shells without leaving NeoSwarm.</Typography>
          </Box>
          <Button variant="contained" startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <AddIcon />} onClick={() => void handleCreate()} disabled={saving}>
            New terminal
          </Button>
        </Box>
        <Typography sx={{ color: c.text.ghost, fontSize: '0.76rem', mb: 2 }}>Terminals run locally in their selected working directory. Closing a tab stops its process.</Typography>

        {error && <Alert severity="error" onClose={() => dispatch(clearTerminalError())} sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mb: 1, overflowX: 'auto', minHeight: 42 }}>
          {terminals.map((terminal) => {
            const selected = terminal.id === activeId;
            return (
              <Box
                key={terminal.id}
                onClick={() => dispatch(setActiveTerminal(terminal.id))}
                sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0, maxWidth: 260, px: 1.25, py: 0.7, borderRadius: 1.5, cursor: 'pointer', bgcolor: selected ? `${c.accent.primary}18` : c.bg.surface, border: `1px solid ${selected ? `${c.accent.primary}55` : c.border.subtle}`, color: selected ? c.text.primary : c.text.tertiary }}
              >
                <TerminalOutlinedIcon sx={{ fontSize: 16 }} />
                <Typography sx={{ fontSize: '0.76rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 190 }}>{terminal.title}</Typography>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: terminal.status === 'running' ? c.status.success : c.text.ghost }} />
                <IconButton size="small" aria-label={`Close ${terminal.title}`} onClick={(event) => { event.stopPropagation(); void handleDelete(terminal); }} sx={{ p: 0.15, color: c.text.ghost }}>
                  <CloseIcon sx={{ fontSize: 15 }} />
                </IconButton>
              </Box>
            );
          })}
          {terminals.length === 0 && !loading && <Typography sx={{ color: c.text.ghost, fontSize: '0.78rem' }}>No terminal tabs open.</Typography>}
        </Box>

        <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
          <TextField label="Working directory for new terminal" value={cwd} onChange={(event) => setCwd(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void handleCreate(); }} size="small" fullWidth />
        </Box>

        {loading && terminals.length === 0 ? (
          <Box sx={{ flex: 1, display: 'grid', placeItems: 'center' }}><CircularProgress size={24} /></Box>
        ) : active ? (
          <Box sx={{ flex: 1, minHeight: 420, display: 'flex', flexDirection: 'column', border: `1px solid ${c.border.subtle}`, borderRadius: 3, overflow: 'hidden', bgcolor: '#101114' }}>
            <Box sx={{ px: 1.5, py: 0.8, display: 'flex', alignItems: 'center', gap: 1, bgcolor: c.bg.surface, borderBottom: `1px solid ${c.border.subtle}` }}>
              <Typography sx={{ color: c.text.primary, fontSize: '0.78rem', fontWeight: 600 }}>{active.title}</Typography>
              <Chip label={active.status} size="small" sx={{ height: 20, fontSize: '0.65rem', color: active.status === 'running' ? c.status.success : c.text.ghost }} />
              <Typography sx={{ flex: 1, minWidth: 0, color: c.text.ghost, fontSize: '0.68rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{active.cwd}</Typography>
              <Tooltip title="Clear output"><IconButton size="small" onClick={() => dispatch(clearTerminalOutput(active.id))}><ClearAllOutlinedIcon sx={{ fontSize: 17 }} /></IconButton></Tooltip>
              {active.status === 'running' ? (
                <Tooltip title="Interrupt (Ctrl-C)"><IconButton size="small" onClick={() => void send({ type: 'interrupt' })}><StopCircleOutlinedIcon sx={{ fontSize: 17 }} /></IconButton></Tooltip>
              ) : (
                <Tooltip title="Restart terminal"><IconButton size="small" onClick={() => void handleStart(active)}><PlayArrowOutlinedIcon sx={{ fontSize: 17 }} /></IconButton></Tooltip>
              )}
            </Box>
            <Box ref={outputRef} sx={{ flex: 1, minHeight: 0, overflow: 'auto', p: 2, color: '#e7e7e9', fontFamily: c.font.mono, fontSize: '0.78rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {outputs[active.id] || (active.status === 'running' ? 'Connecting to terminal…' : 'Terminal is stopped. Press restart to open it again.')}
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1, bgcolor: c.bg.surface, borderTop: `1px solid ${c.border.subtle}` }}>
              <Typography sx={{ color: c.accent.primary, fontFamily: c.font.mono, fontSize: '0.8rem' }}>›</Typography>
              <TextField
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    handleSubmit();
                  }
                }}
                disabled={active.status !== 'running'}
                placeholder={active.status === 'running' ? 'Type a command and press Enter' : 'Restart this terminal to continue'}
                size="small"
                fullWidth
                autoComplete="off"
                sx={{ '& .MuiOutlinedInput-root': { bgcolor: '#181a1f' }, '& input': { fontFamily: c.font.mono, fontSize: '0.78rem' } }}
              />
            </Box>
          </Box>
        ) : (
          <Box sx={{ flex: 1, minHeight: 420, display: 'grid', placeItems: 'center', p: 5, textAlign: 'center', border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
            <Box>
              <TerminalOutlinedIcon sx={{ fontSize: 48, color: c.text.ghost, mb: 1 }} />
              <Typography sx={{ color: c.text.primary, fontWeight: 650 }}>No terminal tabs</Typography>
              <Typography sx={{ color: c.text.tertiary, fontSize: '0.84rem', mt: 0.5, mb: 2 }}>Create a local shell tab to work alongside your agents.</Typography>
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => void handleCreate()} disabled={saving}>New terminal</Button>
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default Terminals;
