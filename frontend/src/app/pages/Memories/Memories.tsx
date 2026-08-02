import React, { useEffect, useState } from 'react';
import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControl from '@mui/material/FormControl';
import IconButton from '@mui/material/IconButton';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined';
import CloseIcon from '@mui/icons-material/Close';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import {
  clearMemoryError,
  createMemory,
  deleteMemory,
  fetchMemories,
  MemoryCategory,
  updateMemory,
} from '@/shared/state/memoriesSlice';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

const CATEGORIES: Array<{ value: MemoryCategory; label: string }> = [
  { value: 'fact', label: 'Fact' },
  { value: 'preference', label: 'Preference' },
  { value: 'instruction', label: 'Instruction' },
  { value: 'note', label: 'Note' },
];

function parseTags(value: string): string[] {
  return [...new Set(value.split(',').map((tag) => tag.trim()).filter(Boolean))];
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const Memories: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const memories = useAppSelector((state) => state.memories.items);
  const loading = useAppSelector((state) => state.memories.loading);
  const saving = useAppSelector((state) => state.memories.saving);
  const error = useAppSelector((state) => state.memories.error);

  const [query, setQuery] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState<MemoryCategory>('fact');
  const [tags, setTags] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [editingCategory, setEditingCategory] = useState<MemoryCategory>('fact');
  const [editingTags, setEditingTags] = useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => dispatch(fetchMemories(query)), 250);
    return () => window.clearTimeout(timer);
  }, [dispatch, query]);

  const handleCreate = async () => {
    if (!content.trim()) return;
    const result = await dispatch(createMemory({ content: content.trim(), category, tags: parseTags(tags) }));
    if (createMemory.fulfilled.match(result)) {
      setContent('');
      setTags('');
    }
  };

  const beginEdit = (id: string) => {
    const memory = memories[id];
    if (!memory) return;
    setEditingId(id);
    setEditingContent(memory.content);
    setEditingCategory(memory.category);
    setEditingTags(memory.tags.join(', '));
  };

  const saveEdit = async () => {
    if (!editingId || !editingContent.trim()) return;
    const result = await dispatch(updateMemory({
      id: editingId,
      content: editingContent.trim(),
      category: editingCategory,
      tags: parseTags(editingTags),
    }));
    if (updateMemory.fulfilled.match(result)) setEditingId(null);
  };

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1000, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <PsychologyOutlinedIcon />
          </Box>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>Memory</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>
              Keep useful context between sessions. Memories stay local and are injected only when relevant.
            </Typography>
          </Box>
        </Box>
        <Typography sx={{ color: c.text.ghost, fontSize: '0.76rem', mb: 3 }}>
          The agent can search memories, but only saves or removes them when you explicitly ask.
        </Typography>

        {error && <Alert severity="error" onClose={() => dispatch(clearMemoryError())} sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ p: 2.5, mb: 3, borderRadius: 3, border: `1px solid ${c.border.subtle}`, bgcolor: c.bg.surface, boxShadow: c.shadow.sm }}>
          <TextField label="What should NeoSwarm remember?" value={content} onChange={(event) => setContent(event.target.value)} multiline minRows={2} fullWidth sx={{ mb: 2 }} />
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
            <FormControl size="small">
              <InputLabel>Category</InputLabel>
              <Select value={category} label="Category" onChange={(event) => setCategory(event.target.value as MemoryCategory)}>
                {CATEGORIES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField label="Tags (comma separated)" value={tags} onChange={(event) => setTags(event.target.value)} size="small" />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
            <Button variant="contained" startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <AddIcon />} disabled={saving || !content.trim()} onClick={handleCreate}>Save memory</Button>
          </Box>
        </Box>

        <TextField label="Search memories" value={query} onChange={(event) => setQuery(event.target.value)} fullWidth size="small" sx={{ mb: 1.5 }} />
        {loading && Object.keys(memories).length === 0 ? <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }}><CircularProgress size={24} /></Box> : Object.values(memories).length === 0 ? (
          <Box sx={{ p: 5, textAlign: 'center', border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
            <Typography sx={{ color: c.text.tertiary }}>{query ? 'No matching memories.' : 'No memories saved yet.'}</Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'grid', gap: 1.5 }}>
            {Object.values(memories).map((memory) => {
              const editing = editingId === memory.id;
              return (
                <Box key={memory.id} sx={{ p: 2, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
                  {editing ? (
                    <>
                      <TextField value={editingContent} onChange={(event) => setEditingContent(event.target.value)} multiline minRows={2} fullWidth sx={{ mb: 1.5 }} />
                      <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
                        <FormControl size="small" sx={{ minWidth: 150 }}>
                          <InputLabel>Category</InputLabel>
                          <Select value={editingCategory} label="Category" onChange={(event) => setEditingCategory(event.target.value as MemoryCategory)}>
                            {CATEGORIES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
                          </Select>
                        </FormControl>
                        <TextField label="Tags" value={editingTags} onChange={(event) => setEditingTags(event.target.value)} size="small" sx={{ flex: 1, minWidth: 180 }} />
                        <Button size="small" startIcon={<SaveOutlinedIcon />} onClick={saveEdit} disabled={saving || !editingContent.trim()}>Save</Button>
                        <Button size="small" startIcon={<CloseIcon />} onClick={() => setEditingId(null)}>Cancel</Button>
                      </Box>
                    </>
                  ) : (
                    <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75, flexWrap: 'wrap' }}>
                          <Chip label={memory.category} size="small" sx={{ height: 21, fontSize: '0.65rem', color: c.accent.primary, bgcolor: `${c.accent.primary}14` }} />
                          {memory.tags.map((tag) => <Chip key={tag} label={tag} size="small" variant="outlined" sx={{ height: 21, fontSize: '0.65rem' }} />)}
                        </Box>
                        <Typography sx={{ color: c.text.primary, fontSize: '0.88rem', whiteSpace: 'pre-wrap' }}>{memory.content}</Typography>
                        <Typography sx={{ mt: 0.75, color: c.text.ghost, fontSize: '0.68rem' }}>Updated {formatDate(memory.updated_at)}</Typography>
                      </Box>
                      <Box sx={{ display: 'flex', gap: 0.25 }}>
                        <IconButton size="small" onClick={() => beginEdit(memory.id)} aria-label="Edit memory"><EditOutlinedIcon fontSize="small" /></IconButton>
                        <IconButton size="small" color="error" onClick={() => dispatch(deleteMemory(memory.id))} aria-label="Delete memory"><DeleteOutlineIcon fontSize="small" /></IconButton>
                      </Box>
                    </Box>
                  )}
                </Box>
              );
            })}
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default Memories;
