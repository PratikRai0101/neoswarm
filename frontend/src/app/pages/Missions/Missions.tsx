import React, { useEffect, useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Checkbox from '@mui/material/Checkbox';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import FormControlLabel from '@mui/material/FormControlLabel';
import LinearProgress from '@mui/material/LinearProgress';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Slider from '@mui/material/Slider';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import StopCircleOutlinedIcon from '@mui/icons-material/StopCircleOutlined';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import ScheduleIcon from '@mui/icons-material/Schedule';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import {
  cancelMission,
  clearMissionError,
  createMission,
  fetchMission,
  fetchMissions,
  Mission,
  MissionStatus,
  startMission,
} from '@/shared/state/missionsSlice';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

interface ModelChoice {
  key: string;
  provider: string;
  model: string;
  label: string;
}

const ACTIVE_STATUSES = new Set<MissionStatus>(['pending', 'decomposing', 'running']);

function elapsed(createdAt: string, completedAt: string | null): string {
  const seconds = Math.max(
    0,
    Math.round((new Date(completedAt || Date.now()).getTime() - new Date(createdAt).getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

const Missions: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const missions = useAppSelector((state) => state.missions.items);
  const loading = useAppSelector((state) => state.missions.loading);
  const creating = useAppSelector((state) => state.missions.creating);
  const error = useAppSelector((state) => state.missions.error);
  const modelsByProvider = useAppSelector((state) => state.models.byProvider);
  const defaultModel = useAppSelector((state) => state.settings.data.default_model);
  const defaultFolder = useAppSelector((state) => state.settings.data.default_folder);

  const [prompt, setPrompt] = useState('');
  const [workers, setWorkers] = useState(3);
  const [executionMode, setExecutionMode] = useState<'parallel' | 'sequential'>('parallel');
  const [modelKey, setModelKey] = useState('');
  const [targetDirectory, setTargetDirectory] = useState(defaultFolder || '');
  const [isolateWorkers, setIsolateWorkers] = useState(false);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);

  const modelChoices = useMemo<ModelChoice[]>(
    () =>
      Object.entries(modelsByProvider).flatMap(([provider, models]) =>
        models.map((model) => ({
          key: `${provider}::${model.value}`,
          provider: provider.toLowerCase(),
          model: model.value,
          label: `${provider} · ${model.label}`,
        })),
      ),
    [modelsByProvider],
  );

  useEffect(() => {
    dispatch(fetchMissions());
  }, [dispatch]);

  useEffect(() => {
    if (modelKey || modelChoices.length === 0) return;
    const preferred = modelChoices.find((choice) => choice.model === defaultModel);
    setModelKey((preferred || modelChoices[0]).key);
  }, [modelChoices, modelKey, defaultModel]);

  const orderedMissions = useMemo(
    () =>
      Object.values(missions).sort(
        (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      ),
    [missions],
  );

  useEffect(() => {
    if (!selectedMissionId && orderedMissions[0]) setSelectedMissionId(orderedMissions[0].id);
  }, [orderedMissions, selectedMissionId]);

  const activeIds = useMemo(
    () => orderedMissions.filter((mission) => ACTIVE_STATUSES.has(mission.status)).map((mission) => mission.id),
    [orderedMissions],
  );
  const activeIdsKey = activeIds.join(',');

  useEffect(() => {
    if (!activeIdsKey) return;
    const poll = () => activeIds.forEach((missionId) => dispatch(fetchMission(missionId)));
    const timer = window.setInterval(poll, 1200);
    return () => window.clearInterval(timer);
  }, [dispatch, activeIdsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedMission = selectedMissionId ? missions[selectedMissionId] : orderedMissions[0];

  const handleLaunch = async () => {
    const choice = modelChoices.find((candidate) => candidate.key === modelKey);
    if (!choice || !prompt.trim()) return;
    const created = await dispatch(
      createMission({
        mission: prompt.trim(),
        workers,
        model: choice.model,
        provider: choice.provider,
        execution_mode: executionMode,
        target_directory: targetDirectory.trim() || null,
        isolate_workers: isolateWorkers,
      }),
    );
    if (!createMission.fulfilled.match(created)) return;
    setSelectedMissionId(created.payload.id);
    setPrompt('');
    await dispatch(startMission(created.payload.id));
  };

  const statusStyle = (status: MissionStatus) => {
    if (status === 'completed') return { color: c.status.success, background: c.status.successBg };
    if (status === 'failed') return { color: c.status.error, background: c.status.errorBg };
    if (status === 'cancelled') return { color: c.text.tertiary, background: c.bg.secondary };
    if (status === 'running' || status === 'decomposing') {
      return { color: c.status.info, background: c.status.infoBg };
    }
    return { color: c.status.warning, background: c.status.warningBg };
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1320, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
          <Box
            sx={{
              width: 42,
              height: 42,
              borderRadius: 2.5,
              display: 'grid',
              placeItems: 'center',
              color: c.accent.primary,
              bgcolor: `${c.accent.primary}18`,
            }}
          >
            <RocketLaunchIcon />
          </Box>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>
              Missions
            </Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>
              Break a goal into focused work and coordinate agents in parallel or sequence.
            </Typography>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" onClose={() => dispatch(clearMissionError())} sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Box
          sx={{
            p: 2.5,
            mb: 3,
            borderRadius: 3,
            border: `1px solid ${c.border.subtle}`,
            bgcolor: c.bg.surface,
            boxShadow: c.shadow.sm,
          }}
        >
          <TextField
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe the outcome the swarm should deliver..."
            multiline
            minRows={3}
            fullWidth
            disabled={creating}
            sx={{
              mb: 2,
              '& .MuiOutlinedInput-root': { bgcolor: c.bg.page },
            }}
          />

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'minmax(220px, 1.4fr) 1fr 1fr minmax(180px, 1fr)' },
              gap: 2,
              alignItems: 'center',
            }}
          >
            <FormControl size="small" disabled={modelChoices.length === 0 || creating}>
              <InputLabel>Model</InputLabel>
              <Select value={modelKey} label="Model" onChange={(event) => setModelKey(event.target.value)}>
                {modelChoices.map((choice) => (
                  <MenuItem key={choice.key} value={choice.key}>
                    {choice.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Box>
              <Typography sx={{ fontSize: '0.72rem', color: c.text.tertiary, mb: 0.25 }}>
                Workers: {workers}
              </Typography>
              <Slider
                value={workers}
                onChange={(_, value) => setWorkers(value as number)}
                min={1}
                max={8}
                step={1}
                marks
                size="small"
                disabled={creating}
              />
            </Box>

            <ToggleButtonGroup
              value={executionMode}
              exclusive
              fullWidth
              size="small"
              onChange={(_, value) => value && setExecutionMode(value)}
              disabled={creating}
            >
              <ToggleButton value="parallel">Parallel</ToggleButton>
              <ToggleButton value="sequential">Sequential</ToggleButton>
            </ToggleButtonGroup>

            <Button
              variant="contained"
              startIcon={creating ? <CircularProgress size={16} color="inherit" /> : <RocketLaunchIcon />}
              disabled={creating || !prompt.trim() || !modelKey}
              onClick={handleLaunch}
              sx={{ height: 40, bgcolor: c.accent.primary, '&:hover': { bgcolor: c.accent.hover } }}
            >
              Launch mission
            </Button>
          </Box>

          <TextField
            label="Working directory (optional)"
            value={targetDirectory}
            onChange={(event) => setTargetDirectory(event.target.value)}
            placeholder="Uses your default folder when blank"
            size="small"
            fullWidth
            disabled={creating}
            sx={{ mt: 2 }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={isolateWorkers}
                onChange={(event) => setIsolateWorkers(event.target.checked)}
                disabled={creating || !targetDirectory.trim()}
              />
            }
            label="Give each worker an isolated git worktree"
            sx={{ mt: 1, '& .MuiFormControlLabel-label': { fontSize: '0.8rem', color: c.text.secondary } }}
          />
          {isolateWorkers && (
            <Typography sx={{ ml: 4, mt: -0.5, fontSize: '0.72rem', color: c.text.tertiary }}>
              Worktrees are created under &lt;repository&gt;/.worktrees and preserved when they contain uncommitted changes.
            </Typography>
          )}
          {modelChoices.length === 0 && (
            <Typography sx={{ mt: 1.5, fontSize: '0.8rem', color: c.status.warning }}>
              Configure a model provider in Settings or start Ollama before launching a mission.
            </Typography>
          )}
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '360px 1fr' }, gap: 2.5 }}>
          <Box
            sx={{
              borderRadius: 3,
              border: `1px solid ${c.border.subtle}`,
              bgcolor: c.bg.surface,
              overflow: 'hidden',
              alignSelf: 'start',
            }}
          >
            <Typography sx={{ px: 2, py: 1.5, fontWeight: 600, color: c.text.primary }}>
              Recent missions
            </Typography>
            <Box sx={{ borderTop: `1px solid ${c.border.subtle}` }}>
              {loading && orderedMissions.length === 0 ? (
                <Box sx={{ py: 6, display: 'grid', placeItems: 'center' }}><CircularProgress size={24} /></Box>
              ) : orderedMissions.length === 0 ? (
                <Typography sx={{ p: 3, textAlign: 'center', color: c.text.tertiary, fontSize: '0.85rem' }}>
                  No missions yet. Launch one above.
                </Typography>
              ) : (
                orderedMissions.map((mission) => (
                  <Box
                    key={mission.id}
                    onClick={() => setSelectedMissionId(mission.id)}
                    sx={{
                      px: 2,
                      py: 1.5,
                      cursor: 'pointer',
                      borderBottom: `1px solid ${c.border.subtle}`,
                      bgcolor: selectedMission?.id === mission.id ? `${c.accent.primary}0E` : 'transparent',
                      '&:hover': { bgcolor: `${c.accent.primary}0A` },
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
                      <Typography
                        sx={{
                          flex: 1,
                          fontSize: '0.86rem',
                          fontWeight: 600,
                          color: c.text.primary,
                          overflow: 'hidden',
                          whiteSpace: 'nowrap',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {mission.mission}
                      </Typography>
                      <Chip label={mission.status} size="small" sx={{ height: 21, fontSize: '0.65rem', ...statusStyle(mission.status) }} />
                    </Box>
                    <Typography sx={{ fontSize: '0.72rem', color: c.text.tertiary }}>
                      {mission.provider}/{mission.model} · {mission.workers.length} workers · {elapsed(mission.created_at, mission.completed_at)}
                    </Typography>
                  </Box>
                ))
              )}
            </Box>
          </Box>

          <MissionDetail mission={selectedMission} onCancel={(id) => dispatch(cancelMission(id))} />
        </Box>
      </Box>
    </Box>
  );
};

const MissionDetail: React.FC<{ mission?: Mission; onCancel: (missionId: string) => void }> = ({ mission, onCancel }) => {
  const c = useClaudeTokens();
  if (!mission) {
    return (
      <Box sx={{ border: `1px solid ${c.border.subtle}`, bgcolor: c.bg.surface, borderRadius: 3, p: 6, textAlign: 'center' }}>
        <GroupsOutlinedIcon sx={{ fontSize: 42, color: c.text.ghost, mb: 1 }} />
        <Typography sx={{ color: c.text.tertiary }}>Select or launch a mission to inspect its workers.</Typography>
      </Box>
    );
  }

  const completed = mission.tasks.filter((task) => task.status === 'completed').length;
  const progress = mission.tasks.length ? (completed / mission.tasks.length) * 100 : 0;
  const active = ACTIVE_STATUSES.has(mission.status);

  return (
    <Box sx={{ border: `1px solid ${c.border.subtle}`, bgcolor: c.bg.surface, borderRadius: 3, overflow: 'hidden' }}>
      <Box sx={{ p: 2.5, display: 'flex', alignItems: 'flex-start', gap: 2 }}>
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ color: c.text.primary, fontSize: '1rem', fontWeight: 650, mb: 0.5 }}>
            {mission.mission}
          </Typography>
          <Typography sx={{ color: c.text.tertiary, fontSize: '0.78rem' }}>
            {mission.execution_mode} · {mission.provider}/{mission.model} · {mission.isolate_workers ? 'isolated worktrees · ' : ''}{elapsed(mission.created_at, mission.completed_at)}
          </Typography>
        </Box>
        {active && (
          <Button color="error" size="small" startIcon={<StopCircleOutlinedIcon />} onClick={() => onCancel(mission.id)}>
            Cancel
          </Button>
        )}
      </Box>

      {active && <LinearProgress variant={mission.tasks.length ? 'determinate' : 'indeterminate'} value={progress} />}

      <Box sx={{ p: 2.5, borderTop: `1px solid ${c.border.subtle}` }}>
        <Typography sx={{ color: c.text.primary, fontWeight: 600, fontSize: '0.82rem', mb: 1.5 }}>
          Tasks {mission.tasks.length ? `(${completed}/${mission.tasks.length})` : ''}
        </Typography>
        {mission.tasks.length === 0 ? (
          <Typography sx={{ color: c.text.tertiary, fontSize: '0.8rem' }}>
            {mission.status === 'decomposing' ? 'The orchestrator is decomposing the mission…' : 'Waiting to start…'}
          </Typography>
        ) : (
          <Box sx={{ display: 'grid', gap: 1 }}>
            {mission.tasks.map((task) => {
              const Icon = task.status === 'completed' ? CheckCircleOutlineIcon : task.status === 'failed' ? ErrorOutlineIcon : ScheduleIcon;
              const color = task.status === 'completed' ? c.status.success : task.status === 'failed' ? c.status.error : c.text.tertiary;
              return (
                <Box key={task.id} sx={{ display: 'flex', gap: 1.25, p: 1.25, borderRadius: 2, bgcolor: c.bg.secondary }}>
                  <Icon sx={{ mt: 0.2, fontSize: 18, color }} />
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography sx={{ fontSize: '0.8rem', fontWeight: 550, color: c.text.primary }}>
                      {task.description}
                    </Typography>
                    {(task.error || task.result) && (
                      <Typography
                        sx={{ mt: 0.5, whiteSpace: 'pre-wrap', fontSize: '0.74rem', color: task.error ? c.status.error : c.text.tertiary }}
                      >
                        {(task.error || task.result || '').slice(0, 1200)}
                      </Typography>
                    )}
                  </Box>
                  <Typography sx={{ fontSize: '0.68rem', color, textTransform: 'capitalize' }}>{task.status}</Typography>
                </Box>
              );
            })}
          </Box>
        )}
      </Box>

      {mission.final_result && (
        <Box sx={{ p: 2.5, borderTop: `1px solid ${c.border.subtle}`, bgcolor: c.bg.elevated }}>
          <Typography sx={{ fontSize: '0.82rem', fontWeight: 600, color: c.text.primary, mb: 1 }}>Final result</Typography>
          <Typography sx={{ whiteSpace: 'pre-wrap', fontSize: '0.8rem', lineHeight: 1.6, color: c.text.secondary }}>
            {mission.final_result}
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default Missions;
