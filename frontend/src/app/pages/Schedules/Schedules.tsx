import React, { useEffect, useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import AddAlarmIcon from '@mui/icons-material/AddAlarm';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseCircleOutlineIcon from '@mui/icons-material/PauseCircleOutline';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import {
  clearScheduleError,
  createSchedule,
  deleteSchedule,
  fetchSchedules,
  runSchedule,
  updateSchedule,
} from '@/shared/state/schedulesSlice';
import { flattenModelCatalog } from '@/shared/models';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

function localDateInput(): string {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  return date.toISOString().slice(0, 16);
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const Schedules: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const schedules = useAppSelector((state) => state.schedules.items);
  const loading = useAppSelector((state) => state.schedules.loading);
  const saving = useAppSelector((state) => state.schedules.saving);
  const error = useAppSelector((state) => state.schedules.error);
  const modelsByProvider = useAppSelector((state) => state.models.byProvider);
  const defaultModel = useAppSelector((state) => state.settings.data.default_model);
  const defaultFolder = useAppSelector((state) => state.settings.data.default_folder);

  const modelChoices = useMemo(() => flattenModelCatalog(modelsByProvider), [modelsByProvider]);
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [kind, setKind] = useState<'interval' | 'once'>('interval');
  const [intervalSeconds, setIntervalSeconds] = useState('3600');
  const [runAt, setRunAt] = useState(localDateInput);
  const [modelKey, setModelKey] = useState('');
  const [targetDirectory, setTargetDirectory] = useState(defaultFolder || '');

  const modelChoice = modelChoices.find((choice) => `${choice.group}::${choice.value}` === modelKey)
    || modelChoices.find((choice) => choice.value === defaultModel)
    || modelChoices[0];

  useEffect(() => {
    dispatch(fetchSchedules());
  }, [dispatch]);

  useEffect(() => {
    if (modelChoice && !modelKey) setModelKey(`${modelChoice.group}::${modelChoice.value}`);
  }, [modelChoice, modelKey]);

  const activeSchedules = Object.values(schedules).filter((schedule) => schedule.status === 'running');
  useEffect(() => {
    if (activeSchedules.length === 0) return;
    const timer = window.setInterval(() => dispatch(fetchSchedules()), 1200);
    return () => window.clearInterval(timer);
  }, [dispatch, activeSchedules.length]);

  const handleCreate = async () => {
    if (!name.trim() || !prompt.trim() || !modelChoice) return;
    const result = await dispatch(createSchedule({
      name: name.trim(),
      prompt: prompt.trim(),
      kind,
      ...(kind === 'interval'
        ? { interval_seconds: Math.max(10, Number(intervalSeconds) || 10) }
        : { run_at: new Date(runAt).toISOString() }),
      model: modelChoice.value,
      provider: modelChoice.provider,
      target_directory: targetDirectory.trim() || null,
    }));
    if (createSchedule.fulfilled.match(result)) {
      setName('');
      setPrompt('');
    }
  };

  const statusStyle = (status: string) => {
    if (status === 'running') return { color: c.status.info, bgcolor: c.status.infoBg };
    if (status === 'completed' || status === 'scheduled') return { color: c.status.success, bgcolor: c.status.successBg };
    if (status === 'failed') return { color: c.status.error, bgcolor: c.status.errorBg };
    return { color: c.text.tertiary, bgcolor: c.bg.secondary };
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1180, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <AddAlarmIcon />
          </Box>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>Automations</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>
              Run agent prompts on a durable interval or at a specific time.
            </Typography>
          </Box>
        </Box>

        {error && <Alert severity="error" onClose={() => dispatch(clearScheduleError())} sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ p: 2.5, mb: 3, borderRadius: 3, border: `1px solid ${c.border.subtle}`, bgcolor: c.bg.surface, boxShadow: c.shadow.sm }}>
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} fullWidth sx={{ mb: 2 }} />
          <TextField label="Prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} multiline minRows={3} fullWidth sx={{ mb: 2 }} />
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' }, gap: 2, alignItems: 'center' }}>
            <ToggleButtonGroup value={kind} exclusive fullWidth size="small" onChange={(_, value) => value && setKind(value)}>
              <ToggleButton value="interval">Interval</ToggleButton>
              <ToggleButton value="once">One time</ToggleButton>
            </ToggleButtonGroup>
            {kind === 'interval' ? (
              <TextField label="Every (seconds)" type="number" value={intervalSeconds} onChange={(event) => setIntervalSeconds(event.target.value)} inputProps={{ min: 10 }} size="small" />
            ) : (
              <TextField label="Run at" type="datetime-local" value={runAt} onChange={(event) => setRunAt(event.target.value)} InputLabelProps={{ shrink: true }} size="small" />
            )}
            <FormControl size="small" disabled={modelChoices.length === 0}>
              <InputLabel>Model</InputLabel>
              <Select value={modelKey} label="Model" onChange={(event) => setModelKey(event.target.value)}>
                {modelChoices.map((choice) => <MenuItem key={`${choice.group}::${choice.value}`} value={`${choice.group}::${choice.value}`}>{choice.group} · {choice.label}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ display: 'flex', gap: 2, mt: 2, alignItems: 'center' }}>
            <TextField label="Working directory (optional)" value={targetDirectory} onChange={(event) => setTargetDirectory(event.target.value)} fullWidth size="small" />
            <Button variant="contained" startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <AddAlarmIcon />} disabled={saving || !name.trim() || !prompt.trim() || !modelChoice} onClick={handleCreate} sx={{ minWidth: 150, height: 40 }}>Create</Button>
          </Box>
          {modelChoices.length === 0 && <Typography sx={{ mt: 1.5, fontSize: '0.8rem', color: c.status.warning }}>Configure a model provider before creating an automation.</Typography>}
        </Box>

        <Box sx={{ display: 'grid', gap: 1.5 }}>
          {loading && Object.keys(schedules).length === 0 ? <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }}><CircularProgress size={24} /></Box> : Object.values(schedules).length === 0 ? (
            <Box sx={{ p: 5, textAlign: 'center', border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}><Typography sx={{ color: c.text.tertiary }}>No automations yet.</Typography></Box>
          ) : Object.values(schedules).map((schedule) => {
            const style = statusStyle(schedule.status);
            return (
              <Box key={schedule.id} sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography sx={{ fontWeight: 650, color: c.text.primary }}>{schedule.name}</Typography>
                      <Chip label={schedule.status} size="small" sx={{ height: 21, fontSize: '0.65rem', ...style }} />
                    </Box>
                    <Typography sx={{ color: c.text.secondary, fontSize: '0.82rem', whiteSpace: 'pre-wrap' }}>{schedule.prompt}</Typography>
                    <Typography sx={{ mt: 1, color: c.text.tertiary, fontSize: '0.72rem' }}>
                      {schedule.kind === 'interval' ? `Every ${schedule.interval_seconds}s` : `Once at ${formatDate(schedule.run_at)}`} · {schedule.provider || 'auto'}/{schedule.model}
                    </Typography>
                    <Typography sx={{ color: c.text.tertiary, fontSize: '0.72rem' }}>
                      Next: {formatDate(schedule.next_run_at)} · Last: {formatDate(schedule.last_run_at)}
                    </Typography>
                    {schedule.last_error && <Typography sx={{ mt: 0.5, color: c.status.error, fontSize: '0.72rem' }}>{schedule.last_error}</Typography>}
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <Button size="small" startIcon={schedule.enabled ? <PauseCircleOutlineIcon /> : <PlayArrowIcon />} onClick={() => dispatch(updateSchedule({ id: schedule.id, enabled: !schedule.enabled }))} disabled={schedule.status === 'running'}>
                      {schedule.enabled ? 'Disable' : 'Enable'}
                    </Button>
                    <Button size="small" startIcon={<PlayArrowIcon />} onClick={() => dispatch(runSchedule(schedule.id))} disabled={schedule.status === 'running'}>Run</Button>
                    <Button size="small" color="error" startIcon={<DeleteOutlineIcon />} onClick={() => dispatch(deleteSchedule(schedule.id))} disabled={schedule.status === 'running'}>Delete</Button>
                  </Box>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
};

export default Schedules;
