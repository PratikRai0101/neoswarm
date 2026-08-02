import React, { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Typography from '@mui/material/Typography';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import FolderOpenOutlinedIcon from '@mui/icons-material/FolderOpenOutlined';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import { API_BASE } from '@/shared/config';
import { Artifact, deleteArtifact, fetchArtifacts } from '@/shared/state/artifactsSlice';
import { openArtifactInDefaultApp } from '@/shared/tauriArtifacts';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function isTextPreview(artifact: Artifact): boolean {
  return artifact.media_type.startsWith('text/') || [
    'application/json',
    'application/javascript',
    'application/xml',
  ].includes(artifact.media_type);
}

function contentUrl(artifact: Artifact): string {
  return `${API_BASE}/artifacts/${artifact.id}/content`;
}

function downloadUrl(artifact: Artifact): string {
  return `${API_BASE}/artifacts/${artifact.id}/download`;
}

const Artifacts: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const items = useAppSelector((state) => state.artifacts.items);
  const loading = useAppSelector((state) => state.artifacts.loading);
  const error = useAppSelector((state) => state.artifacts.error);
  const artifacts = useMemo(
    () => Object.values(items).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [items],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [textPreview, setTextPreview] = useState<string | null>(null);
  const [textLoading, setTextLoading] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);

  useEffect(() => {
    dispatch(fetchArtifacts());
  }, [dispatch]);

  useEffect(() => {
    if (selectedId && items[selectedId]) return;
    setSelectedId(artifacts[0]?.id ?? null);
  }, [artifacts, items, selectedId]);

  const selected = selectedId ? items[selectedId] : null;

  useEffect(() => {
    if (!selected || !isTextPreview(selected)) {
      setTextPreview(null);
      setTextLoading(false);
      return;
    }
    const controller = new AbortController();
    setTextLoading(true);
    fetch(contentUrl(selected), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Preview failed: ${response.status}`);
        return response.text();
      })
      .then((text) => setTextPreview(text))
      .catch((reason) => {
        if (reason?.name !== 'AbortError') setTextPreview('Unable to load this preview.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setTextLoading(false);
      });
    return () => controller.abort();
  }, [selected]);

  const handleDelete = async (artifact: Artifact) => {
    if (!window.confirm(`Delete ${artifact.filename}?`)) return;
    await dispatch(deleteArtifact(artifact.id));
  };

  const handleOpen = async (artifact: Artifact) => {
    setOpenError(null);
    try {
      await openArtifactInDefaultApp(artifact.id, contentUrl(artifact));
    } catch (reason) {
      setOpenError(reason instanceof Error ? reason.message : 'Could not open artifact.');
    }
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1280, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <Inventory2OutlinedIcon />
          </Box>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>Artifacts</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>
              Preview files that agents publish for you. Everything stays in your local NeoSwarm data directory.
            </Typography>
          </Box>
        </Box>
        <Typography sx={{ color: c.text.ghost, fontSize: '0.76rem', mb: 3 }}>
          Ask an agent to publish a generated file when you want it available here.
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {openError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setOpenError(null)}>{openError}</Alert>}

        {loading && artifacts.length === 0 ? (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 8 }}><CircularProgress size={24} /></Box>
        ) : artifacts.length === 0 ? (
          <Box sx={{ p: 7, textAlign: 'center', border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
            <FolderOpenOutlinedIcon sx={{ fontSize: 42, color: c.text.ghost, mb: 1 }} />
            <Typography sx={{ color: c.text.primary, fontWeight: 600 }}>No artifacts yet</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.85rem', mt: 0.5 }}>
              Published PDFs, images, spreadsheets, and text files will appear here.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '300px minmax(0, 1fr)' }, gap: 2, minHeight: 560 }}>
            <Box sx={{ border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface, overflow: 'hidden' }}>
              <Box sx={{ px: 2, py: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography sx={{ color: c.text.primary, fontWeight: 600, fontSize: '0.86rem' }}>Published files</Typography>
                <Chip label={artifacts.length} size="small" sx={{ height: 21, fontSize: '0.68rem' }} />
              </Box>
              <Divider />
              <Box sx={{ maxHeight: 600, overflow: 'auto' }}>
                {artifacts.map((artifact) => {
                  const active = artifact.id === selectedId;
                  return (
                    <Box
                      key={artifact.id}
                      onClick={() => setSelectedId(artifact.id)}
                      sx={{
                        px: 1.5,
                        py: 1.25,
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 1,
                        cursor: 'pointer',
                        bgcolor: active ? `${c.accent.primary}12` : 'transparent',
                        borderLeft: active ? `2px solid ${c.accent.primary}` : '2px solid transparent',
                        '&:hover': { bgcolor: active ? `${c.accent.primary}18` : `${c.text.tertiary}0A` },
                      }}
                    >
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography sx={{ color: active ? c.text.primary : c.text.secondary, fontSize: '0.8rem', fontWeight: active ? 600 : 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {artifact.filename}
                        </Typography>
                        <Typography sx={{ color: c.text.ghost, fontSize: '0.68rem', mt: 0.25 }}>
                          {formatBytes(artifact.size_bytes)} · {artifact.media_type}
                        </Typography>
                      </Box>
                      <IconButton size="small" aria-label={`Delete ${artifact.filename}`} onClick={(event) => { event.stopPropagation(); void handleDelete(artifact); }} sx={{ mt: -0.5 }}>
                        <DeleteOutlineIcon sx={{ fontSize: 17 }} />
                      </IconButton>
                    </Box>
                  );
                })}
              </Box>
            </Box>

            <Box sx={{ border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              {selected ? (
                <>
                  <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ color: c.text.primary, fontWeight: 650, fontSize: '0.95rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selected.filename}</Typography>
                      <Typography sx={{ color: c.text.tertiary, fontSize: '0.72rem', mt: 0.35 }}>{selected.description || 'No description'} · {formatDate(selected.created_at)}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
                      <Button size="small" startIcon={<FolderOpenOutlinedIcon />} onClick={() => void handleOpen(selected)}>Open in default app</Button>
                      <Button component="a" href={downloadUrl(selected)} download={selected.filename} size="small" startIcon={<DownloadOutlinedIcon />}>Download</Button>
                    </Box>
                  </Box>
                  <Divider />
                  <Box sx={{ flex: 1, minHeight: 0, p: 2, display: 'flex', alignItems: 'stretch', justifyContent: 'center', bgcolor: c.bg.page }}>
                    {selected.media_type.startsWith('image/') ? (
                      <Box component="img" src={contentUrl(selected)} alt={selected.filename} sx={{ maxWidth: '100%', maxHeight: 620, objectFit: 'contain', borderRadius: 1.5 }} />
                    ) : selected.media_type === 'application/pdf' ? (
                      <Box component="iframe" title={selected.filename} src={contentUrl(selected)} sx={{ width: '100%', minHeight: 600, border: 0, borderRadius: 1.5, bgcolor: '#fff' }} />
                    ) : isTextPreview(selected) ? (
                      textLoading ? <Box sx={{ display: 'grid', placeItems: 'center', width: '100%' }}><CircularProgress size={24} /></Box> : <Box component="pre" sx={{ m: 0, p: 2, width: '100%', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: c.text.primary, bgcolor: c.bg.surface, borderRadius: 1.5, fontFamily: c.font.mono, fontSize: '0.76rem', lineHeight: 1.55 }}>{textPreview}</Box>
                    ) : (
                      <Box sx={{ display: 'grid', placeItems: 'center', textAlign: 'center', p: 4 }}>
                        <FolderOpenOutlinedIcon sx={{ fontSize: 44, color: c.text.ghost, mb: 1 }} />
                        <Typography sx={{ color: c.text.secondary, fontSize: '0.88rem' }}>Preview is not available for this file type.</Typography>
                        <Button component="a" href={downloadUrl(selected)} download={selected.filename} size="small" startIcon={<DownloadOutlinedIcon />} sx={{ mt: 1.5 }}>Download file</Button>
                      </Box>
                    )}
                  </Box>
                </>
              ) : null}
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default Artifacts;
