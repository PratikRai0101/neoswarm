import React, { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import CloudOutlinedIcon from '@mui/icons-material/CloudOutlined';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import KeyOutlinedIcon from '@mui/icons-material/KeyOutlined';
import TerminalOutlinedIcon from '@mui/icons-material/TerminalOutlined';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import { createTerminal } from '@/shared/state/terminalsSlice';
import { clearSSHError, createSSHProfile, deleteSSHProfile, fetchSSHProfiles } from '@/shared/state/sshSlice';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

const SSH: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const profiles = useAppSelector((state) => Object.values(state.ssh.items));
  const loading = useAppSelector((state) => state.ssh.loading);
  const saving = useAppSelector((state) => state.ssh.saving);
  const terminalSaving = useAppSelector((state) => state.terminals.saving);
  const error = useAppSelector((state) => state.ssh.error);
  const [name, setName] = useState('');
  const [host, setHost] = useState('');
  const [user, setUser] = useState('');
  const [port, setPort] = useState('22');
  const [identityFile, setIdentityFile] = useState('');

  useEffect(() => {
    dispatch(fetchSSHProfiles());
  }, [dispatch]);

  const sortedProfiles = useMemo(
    () => profiles.sort((a, b) => a.name.localeCompare(b.name)),
    [profiles],
  );

  const handleCreate = async () => {
    if (!name.trim() || !host.trim()) return;
    const result = await dispatch(createSSHProfile({
      name: name.trim(),
      host: host.trim(),
      user: user.trim(),
      port: Number(port) || 22,
      identity_file: identityFile.trim() || undefined,
    }));
    if (createSSHProfile.fulfilled.match(result)) {
      setName('');
      setHost('');
      setUser('');
      setPort('22');
      setIdentityFile('');
    }
  };

  const handleOpenTerminal = async (profileId: string) => {
    const result = await dispatch(createTerminal({ ssh_profile_id: profileId }));
    if (createTerminal.fulfilled.match(result)) navigate('/terminals');
  };

  const handleDelete = async (profile: { id: string; name: string }) => {
    if (!window.confirm(`Delete SSH profile "${profile.name}"?`)) return;
    await dispatch(deleteSSHProfile(profile.id));
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1000, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <CloudOutlinedIcon />
          </Box>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>SSH workspaces</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>Save connection profiles and open remote shells in Terminal tabs.</Typography>
          </Box>
        </Box>
        <Typography sx={{ color: c.text.ghost, fontSize: '0.76rem', mb: 3 }}>
          NeoSwarm uses your system SSH client, agent, and known_hosts. Private-key contents are never imported or stored.
        </Typography>

        {error && <Alert severity="error" onClose={() => dispatch(clearSSHError())} sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ p: 2.5, mb: 3, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <AddIcon sx={{ color: c.accent.primary, fontSize: 20 }} />
            <Typography sx={{ color: c.text.primary, fontWeight: 650 }}>Add connection profile</Typography>
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1.5 }}>
            <TextField label="Profile name" value={name} onChange={(event) => setName(event.target.value)} size="small" />
            <TextField label="Host" value={host} onChange={(event) => setHost(event.target.value)} size="small" placeholder="server.example.com" />
            <TextField label="User (optional)" value={user} onChange={(event) => setUser(event.target.value)} size="small" />
            <TextField label="Port" value={port} onChange={(event) => setPort(event.target.value)} size="small" type="number" inputProps={{ min: 1, max: 65535 }} />
            <TextField label="Identity file path (optional)" value={identityFile} onChange={(event) => setIdentityFile(event.target.value)} size="small" fullWidth sx={{ gridColumn: { sm: '1 / -1' } }} placeholder="~/.ssh/id_ed25519" />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
            <Button variant="contained" startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <AddIcon />} disabled={saving || !name.trim() || !host.trim()} onClick={() => void handleCreate()}>Save profile</Button>
          </Box>
        </Box>

        {loading && sortedProfiles.length === 0 ? (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 7 }}><CircularProgress size={24} /></Box>
        ) : sortedProfiles.length === 0 ? (
          <Box sx={{ p: 6, textAlign: 'center', border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
            <KeyOutlinedIcon sx={{ fontSize: 42, color: c.text.ghost, mb: 1 }} />
            <Typography sx={{ color: c.text.primary, fontWeight: 600 }}>No SSH profiles yet</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.84rem', mt: 0.5 }}>Add a host above to open a remote terminal.</Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'grid', gap: 1.5 }}>
            {sortedProfiles.map((profile) => (
              <Box key={profile.id} sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1.5, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                <Box sx={{ width: 36, height: 36, borderRadius: 2, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}14` }}><KeyOutlinedIcon fontSize="small" /></Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ color: c.text.primary, fontWeight: 650, fontSize: '0.88rem' }}>{profile.name}</Typography>
                  <Typography sx={{ color: c.text.tertiary, fontFamily: c.font.mono, fontSize: '0.74rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{profile.target}</Typography>
                  {profile.identity_file && <Typography sx={{ color: c.text.ghost, fontSize: '0.68rem', mt: 0.25 }}>Identity: {profile.identity_file}</Typography>}
                </Box>
                <Chip label="SSH" size="small" sx={{ display: { xs: 'none', sm: 'inline-flex' }, height: 21, fontSize: '0.65rem' }} />
                <Button size="small" variant="outlined" startIcon={terminalSaving ? <CircularProgress size={14} /> : <TerminalOutlinedIcon />} disabled={terminalSaving} onClick={() => void handleOpenTerminal(profile.id)}>Open terminal</Button>
                <IconButton size="small" color="error" aria-label={`Delete ${profile.name}`} onClick={() => void handleDelete(profile)}><DeleteOutlineIcon /></IconButton>
              </Box>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default SSH;
