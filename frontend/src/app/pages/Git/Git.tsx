import React, { useCallback, useEffect, useState } from 'react';
import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AccountTreeOutlinedIcon from '@mui/icons-material/AccountTreeOutlined';
import CommitOutlinedIcon from '@mui/icons-material/CommitOutlined';
import OpenInNewOutlinedIcon from '@mui/icons-material/OpenInNewOutlined';
import PublishOutlinedIcon from '@mui/icons-material/PublishOutlined';
import RefreshIcon from '@mui/icons-material/Refresh';
import CodeOutlinedIcon from '@mui/icons-material/CodeOutlined';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import {
  clearGitError,
  createGitCommit,
  createGitPullRequest,
  fetchGitBranches,
  fetchGitDiff,
  fetchGitRemotes,
  fetchGitStatus,
  pushGitBranch,
} from '@/shared/state/gitSlice';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

const Git: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const status = useAppSelector((state) => state.git.status);
  const diff = useAppSelector((state) => state.git.diff);
  const branches = useAppSelector((state) => state.git.branches);
  const remotes = useAppSelector((state) => state.git.remotes);
  const pushing = useAppSelector((state) => state.git.pushing);
  const creatingPullRequest = useAppSelector((state) => state.git.creatingPullRequest);
  const lastPush = useAppSelector((state) => state.git.lastPush);
  const lastPullRequest = useAppSelector((state) => state.git.lastPullRequest);
  const loading = useAppSelector((state) => state.git.loading);
  const committing = useAppSelector((state) => state.git.committing);
  const error = useAppSelector((state) => state.git.error);
  const defaultFolder = useAppSelector((state) => state.settings.data.default_folder);
  const [path, setPath] = useState(defaultFolder || '.');
  const [message, setMessage] = useState('');
  const [stageAll, setStageAll] = useState(false);
  const [remote, setRemote] = useState('origin');
  const [pullRequestTitle, setPullRequestTitle] = useState('');
  const [pullRequestBody, setPullRequestBody] = useState('');
  const [pullRequestBase, setPullRequestBase] = useState('main');
  const [pullRequestDraft, setPullRequestDraft] = useState(false);

  const refresh = useCallback(() => {
    dispatch(fetchGitStatus(path));
    dispatch(fetchGitBranches(path));
    dispatch(fetchGitRemotes(path));
    dispatch(fetchGitDiff({ path }));
  }, [dispatch, path]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (remotes.length > 0 && !remotes.some((item) => item.name === remote)) {
      setRemote(remotes[0].name);
    }
  }, [remotes, remote]);

  const handleCommit = async () => {
    if (!message.trim()) return;
    const result = await dispatch(createGitCommit({ path, message: message.trim(), stageAll }));
    if (createGitCommit.fulfilled.match(result)) {
      setMessage('');
      setStageAll(false);
      refresh();
    }
  };

  const handlePush = async () => {
    if (!status?.branch || !remote) return;
    const result = await dispatch(pushGitBranch({ path, remote, branch: status.branch, setUpstream: true }));
    if (pushGitBranch.fulfilled.match(result)) refresh();
  };

  const handleCreatePullRequest = async () => {
    if (!status?.branch || !remote || !pullRequestTitle.trim()) return;
    await dispatch(createGitPullRequest({
      path,
      title: pullRequestTitle.trim(),
      body: pullRequestBody,
      base: pullRequestBase.trim() || 'main',
      head: status.branch,
      remote,
      draft: pullRequestDraft,
    }));
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1180, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <AccountTreeOutlinedIcon />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>Git workspace</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>Inspect changes and create explicit commits without leaving NeoSwarm.</Typography>
          </Box>
          <IconButton onClick={refresh} disabled={loading} aria-label="Refresh Git status"><RefreshIcon /></IconButton>
        </Box>
        <Typography sx={{ color: c.text.ghost, fontSize: '0.76rem', mb: 3 }}>Commit only changes you have reviewed. NeoSwarm never stages or commits automatically.</Typography>

        {error && <Alert severity="error" onClose={() => dispatch(clearGitError())} sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <TextField label="Repository path" value={path} onChange={(event) => setPath(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') refresh(); }} fullWidth size="small" />
          <Button variant="outlined" onClick={refresh} disabled={loading} sx={{ minWidth: 110 }}>Open</Button>
        </Box>

        {status ? (
          <>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mb: 2 }}>
              <Chip icon={<AccountTreeOutlinedIcon />} label={status.branch || 'detached HEAD'} color="primary" variant="outlined" />
              <Chip label={status.clean ? 'Clean' : `${status.entries.length} changed`} size="small" sx={{ color: status.clean ? c.status.success : c.status.warning, bgcolor: status.clean ? c.status.successBg : c.status.warningBg }} />
              {status.ahead > 0 && <Chip label={`${status.ahead} ahead`} size="small" />}
              {status.behind > 0 && <Chip label={`${status.behind} behind`} size="small" />}
              <Typography sx={{ color: c.text.ghost, fontSize: '0.7rem', ml: { sm: 1 } }}>{status.root}</Typography>
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.4fr) minmax(300px, 0.6fr)' }, gap: 2 }}>
              <Box sx={{ minWidth: 0, p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                  <CodeOutlinedIcon sx={{ color: c.text.tertiary, fontSize: 19 }} />
                  <Typography sx={{ color: c.text.primary, fontWeight: 650 }}>Working tree diff</Typography>
                  {diff?.truncated && <Chip label="truncated" size="small" color="warning" />}
                </Box>
                <Box component="pre" sx={{ m: 0, p: 1.5, minHeight: 260, maxHeight: 520, overflow: 'auto', borderRadius: 2, bgcolor: c.bg.page, color: c.text.secondary, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.72rem', lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
                  {diff?.diff || 'No unstaged diff.'}
                </Box>
              </Box>

              <Box sx={{ display: 'grid', gap: 2, alignContent: 'start' }}>
                <Box sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                  <Typography sx={{ color: c.text.primary, fontWeight: 650, mb: 1.5 }}>Changed files</Typography>
                  {status.entries.length === 0 ? <Typography sx={{ color: c.text.tertiary, fontSize: '0.82rem' }}>Working tree is clean.</Typography> : status.entries.map((entry) => (
                    <Box key={`${entry.index}${entry.worktree}${entry.path}`} sx={{ display: 'flex', gap: 1, py: 0.55, borderBottom: `1px solid ${c.border.subtle}` }}>
                      <Typography sx={{ width: 24, color: entry.index !== ' ' ? c.accent.primary : c.status.warning, fontFamily: 'monospace', fontSize: '0.75rem' }}>{entry.index}{entry.worktree}</Typography>
                      <Typography sx={{ color: c.text.secondary, fontSize: '0.78rem', overflow: 'hidden', textOverflow: 'ellipsis' }}>{entry.path}</Typography>
                    </Box>
                  ))}
                </Box>

                <Box sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                  <Typography sx={{ color: c.text.primary, fontWeight: 650, mb: 1.5 }}>Commit reviewed changes</Typography>
                  <TextField label="Commit message" value={message} onChange={(event) => setMessage(event.target.value)} multiline minRows={2} fullWidth size="small" sx={{ mb: 1 }} />
                  <FormControlLabel control={<Checkbox checked={stageAll} onChange={(event) => setStageAll(event.target.checked)} size="small" />} label={<Typography sx={{ fontSize: '0.75rem', color: c.text.tertiary }}>Stage all changes</Typography>} />
                  <Button variant="contained" startIcon={committing ? <CircularProgress size={16} color="inherit" /> : <CommitOutlinedIcon />} disabled={committing || !message.trim() || status.clean} onClick={handleCommit} fullWidth>Commit</Button>
                </Box>

                <Box sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                  <Typography sx={{ color: c.text.primary, fontWeight: 650, mb: 1 }}>Publish branch</Typography>
                  {remotes.length === 0 ? (
                    <Typography sx={{ color: c.text.tertiary, fontSize: '0.78rem' }}>No Git remotes configured.</Typography>
                  ) : (
                    <>
                      <FormControl size="small" fullWidth sx={{ mb: 1 }}>
                        <InputLabel>Remote</InputLabel>
                        <Select value={remote} label="Remote" onChange={(event) => setRemote(event.target.value)}>
                          {remotes.map((item) => <MenuItem key={item.name} value={item.name}>{item.name} · {item.url}</MenuItem>)}
                        </Select>
                      </FormControl>
                      <Button variant="outlined" startIcon={pushing ? <CircularProgress size={16} /> : <PublishOutlinedIcon />} disabled={pushing || !status.branch} onClick={() => void handlePush()} fullWidth>Push {status.branch || 'branch'}</Button>
                      {lastPush && lastPush.path === status.path && <Typography sx={{ color: c.status.success, fontSize: '0.7rem', mt: 0.75 }}>Pushed {lastPush.branch} to {lastPush.remote}.</Typography>}
                    </>
                  )}
                </Box>

                <Box sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                  <Typography sx={{ color: c.text.primary, fontWeight: 650, mb: 1 }}>Create pull request</Typography>
                  <Typography sx={{ color: c.text.ghost, fontSize: '0.7rem', mb: 1 }}>Push the branch first, then open GitHub CLI's authenticated PR flow.</Typography>
                  <TextField label="Title" value={pullRequestTitle} onChange={(event) => setPullRequestTitle(event.target.value)} size="small" fullWidth sx={{ mb: 1 }} />
                  <TextField label="Description" value={pullRequestBody} onChange={(event) => setPullRequestBody(event.target.value)} multiline minRows={2} size="small" fullWidth sx={{ mb: 1 }} />
                  <TextField label="Base branch" value={pullRequestBase} onChange={(event) => setPullRequestBase(event.target.value)} size="small" fullWidth sx={{ mb: 0.5 }} />
                  <FormControlLabel control={<Checkbox checked={pullRequestDraft} onChange={(event) => setPullRequestDraft(event.target.checked)} size="small" />} label={<Typography sx={{ fontSize: '0.75rem', color: c.text.tertiary }}>Create as draft</Typography>} />
                  <Button variant="contained" startIcon={creatingPullRequest ? <CircularProgress size={16} color="inherit" /> : <OpenInNewOutlinedIcon />} disabled={creatingPullRequest || !pullRequestTitle.trim() || !status.branch || remotes.length === 0} onClick={() => void handleCreatePullRequest()} fullWidth>Create pull request</Button>
                  {lastPullRequest && lastPullRequest.path === status.path && <Button component="a" href={lastPullRequest.url} target="_blank" rel="noopener noreferrer" size="small" startIcon={<OpenInNewOutlinedIcon />} sx={{ mt: 0.75 }}>Open {lastPullRequest.url}</Button>}
                </Box>

                <Box sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                  <Typography sx={{ color: c.text.primary, fontWeight: 650, mb: 1 }}>Local branches</Typography>
                  {branches.length === 0 ? <Typography sx={{ color: c.text.tertiary, fontSize: '0.78rem' }}>No local branches found.</Typography> : branches.map((branch) => <Typography key={branch.name} sx={{ color: branch.current ? c.accent.primary : c.text.tertiary, fontSize: '0.78rem', py: 0.25 }}>{branch.current ? '● ' : '○ '}{branch.name}</Typography>)}
                </Box>
              </Box>
            </Box>
          </>
        ) : loading ? <Box sx={{ display: 'grid', placeItems: 'center', py: 8 }}><CircularProgress size={24} /></Box> : null}
      </Box>
    </Box>
  );
};

export default Git;
