import React, { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import ImageOutlinedIcon from '@mui/icons-material/ImageOutlined';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import { API_BASE } from '@/shared/config';
import { clearImageError, generateImage } from '@/shared/state/imagesSlice';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

const Images: React.FC = () => {
  const c = useClaudeTokens();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const generating = useAppSelector((state) => state.images.generating);
  const last = useAppSelector((state) => state.images.last);
  const error = useAppSelector((state) => state.images.error);
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('gpt-image-1.5');
  const [size, setSize] = useState('1024x1024');
  const [quality, setQuality] = useState('medium');
  const [format, setFormat] = useState('png');
  const [background, setBackground] = useState('auto');

  const handleFormatChange = (value: string) => {
    setFormat(value);
    if (value === 'jpeg' && background === 'transparent') setBackground('auto');
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    await dispatch(generateImage({
      prompt: prompt.trim(),
      model,
      size,
      quality,
      output_format: format,
      background,
    }));
  };

  const imageUrl = last ? `${API_BASE}/artifacts/${last.artifact.id}/content` : '';
  const downloadUrl = last ? `${API_BASE}/artifacts/${last.artifact.id}/download` : '';

  return (
    <Box sx={{ height: '100%', overflow: 'auto', p: { xs: 2, lg: 4 } }}>
      <Box sx={{ maxWidth: 1100, mx: 'auto' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
          <Box sx={{ width: 42, height: 42, borderRadius: 2.5, display: 'grid', placeItems: 'center', color: c.accent.primary, bgcolor: `${c.accent.primary}18` }}>
            <ImageOutlinedIcon />
          </Box>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, color: c.text.primary }}>Image generation</Typography>
            <Typography sx={{ color: c.text.tertiary, fontSize: '0.9rem' }}>Create images with OpenAI and keep the results in your local Artifact workspace.</Typography>
          </Box>
        </Box>
        <Typography sx={{ color: c.text.ghost, fontSize: '0.76rem', mb: 3 }}>
          Requires an OpenAI API key. Each generation is an explicit action and may incur provider charges.
        </Typography>

        {error && <Alert severity="error" onClose={() => dispatch(clearImageError())} sx={{ mb: 2 }}>{error}</Alert>}

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(360px, 0.85fr) minmax(0, 1.15fr)' }, gap: 2 }}>
          <Box sx={{ p: 2.5, border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
            <TextField label="Describe the image" value={prompt} onChange={(event) => setPrompt(event.target.value)} multiline minRows={6} fullWidth placeholder="A cinematic editorial illustration of..." />
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5, mt: 2 }}>
              <FormControl size="small"><InputLabel>Model</InputLabel><Select value={model} label="Model" onChange={(event) => setModel(event.target.value)}><MenuItem value="gpt-image-1.5">GPT Image 1.5</MenuItem><MenuItem value="gpt-image-2">GPT Image 2</MenuItem><MenuItem value="gpt-image-1">GPT Image 1</MenuItem><MenuItem value="gpt-image-1-mini">GPT Image 1 Mini</MenuItem></Select></FormControl>
              <FormControl size="small"><InputLabel>Size</InputLabel><Select value={size} label="Size" onChange={(event) => setSize(event.target.value)}><MenuItem value="1024x1024">Square</MenuItem><MenuItem value="1536x1024">Landscape</MenuItem><MenuItem value="1024x1536">Portrait</MenuItem><MenuItem value="auto">Auto</MenuItem></Select></FormControl>
              <FormControl size="small"><InputLabel>Quality</InputLabel><Select value={quality} label="Quality" onChange={(event) => setQuality(event.target.value)}><MenuItem value="low">Low</MenuItem><MenuItem value="medium">Medium</MenuItem><MenuItem value="high">High</MenuItem><MenuItem value="auto">Auto</MenuItem></Select></FormControl>
              <FormControl size="small"><InputLabel>Format</InputLabel><Select value={format} label="Format" onChange={(event) => handleFormatChange(event.target.value)}><MenuItem value="png">PNG</MenuItem><MenuItem value="jpeg">JPEG</MenuItem><MenuItem value="webp">WEBP</MenuItem></Select></FormControl>
              <FormControl size="small" sx={{ gridColumn: '1 / -1' }}><InputLabel>Background</InputLabel><Select value={background} label="Background" onChange={(event) => setBackground(event.target.value)}><MenuItem value="auto">Auto</MenuItem><MenuItem value="opaque">Opaque</MenuItem><MenuItem value="transparent" disabled={format === 'jpeg'}>Transparent</MenuItem></Select></FormControl>
            </Box>
            <Button variant="contained" fullWidth startIcon={generating ? <CircularProgress size={17} color="inherit" /> : <AutoAwesomeOutlinedIcon />} disabled={generating || !prompt.trim()} onClick={() => void handleGenerate()} sx={{ mt: 2 }}>{generating ? 'Generating…' : 'Generate image'}</Button>
          </Box>

          <Box sx={{ minHeight: 520, p: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: `1px solid ${c.border.subtle}`, borderRadius: 3, bgcolor: c.bg.surface }}>
            {last ? (
              <>
                <Box component="img" src={imageUrl} alt={last.artifact.filename} sx={{ maxWidth: '100%', maxHeight: 520, objectFit: 'contain', borderRadius: 2 }} />
                {last.revised_prompt && <Typography sx={{ color: c.text.ghost, fontSize: '0.7rem', mt: 1, textAlign: 'center' }}>{last.revised_prompt}</Typography>}
                <Box sx={{ display: 'flex', gap: 1, mt: 1.5 }}>
                  <Button component="a" href={downloadUrl} download={last.artifact.filename} size="small" startIcon={<DownloadOutlinedIcon />}>Download</Button>
                  <Button size="small" startIcon={<Inventory2OutlinedIcon />} onClick={() => navigate('/artifacts')}>Open Artifacts</Button>
                </Box>
              </>
            ) : (
              <Box sx={{ textAlign: 'center', p: 4 }}>
                <ImageOutlinedIcon sx={{ fontSize: 52, color: c.text.ghost, mb: 1 }} />
                <Typography sx={{ color: c.text.secondary, fontWeight: 600 }}>Your generated image will appear here</Typography>
                <Typography sx={{ color: c.text.tertiary, fontSize: '0.82rem', mt: 0.5 }}>Images are saved locally as Artifacts.</Typography>
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default Images;
