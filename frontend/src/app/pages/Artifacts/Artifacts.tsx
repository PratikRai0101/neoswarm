import React, { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import InputBase from '@mui/material/InputBase';
import Typography from '@mui/material/Typography';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import FolderOpenOutlinedIcon from '@mui/icons-material/FolderOpenOutlined';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import { useAppDispatch, useAppSelector } from '@/shared/hooks';
import { API_BASE } from '@/shared/config';
import { Artifact, deleteArtifact, fetchArtifacts } from '@/shared/state/artifactsSlice';
import { openArtifactInDefaultApp } from '@/shared/tauriArtifacts';
import {
  ArtifactPreview,
  fetchArtifactPreview,
  getPdfView,
  getSheetIndex,
  getSlideIndex,
  isOfficePreview,
  pdfFragment,
  setPdfView,
  setSheetIndex,
  setSlideIndex,
} from '@/shared/artifactPreview';
import { useClaudeTokens } from '@/shared/styles/ThemeContext';

const PDF_ZOOMS = ['auto', '50', '75', '100', '125', '150', '200'];

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

function SheetTable({ rows }: { rows: string[][] }) {
  const c = useClaudeTokens();
  if (rows.length === 0) {
    return <Typography sx={{ color: c.text.ghost, fontSize: '0.8rem' }}>Empty sheet.</Typography>;
  }
  const [header, ...body] = rows;
  return (
    <Box sx={{ overflow: 'auto', maxHeight: 560, border: `1px solid ${c.border.subtle}`, borderRadius: 1.5, bgcolor: c.bg.surface }}>
      <Box
        component="table"
        sx={{ borderCollapse: 'collapse', width: '100%', fontSize: '0.74rem', fontFamily: c.font.mono }}
      >
        <Box component="thead" sx={{ position: 'sticky', top: 0, bgcolor: c.bg.secondary, zIndex: 1 }}>
          <Box component="tr">
            {header.map((cell, i) => (
              <Box component="th" key={i} sx={{ textAlign: 'left', fontWeight: 600, color: c.text.primary, px: 1.25, py: 0.75, borderBottom: `1px solid ${c.border.subtle}`, whiteSpace: 'nowrap' }}>
                {cell || `Col ${i + 1}`}
              </Box>
            ))}
          </Box>
        </Box>
        <Box component="tbody">
          {body.map((row, r) => (
            <Box component="tr" key={r} sx={{ '&:nth-of-type(even)': { bgcolor: `${c.text.tertiary}08` } }}>
              {row.map((cell, i) => (
                <Box component="td" key={i} sx={{ color: c.text.secondary, px: 1.25, py: 0.5, borderBottom: `1px solid ${c.border.subtle}`, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={cell}>
                  {cell}
                </Box>
              ))}
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

function WorkbookPreview({
  preview, artifactId, sheetIdx, onSheet,
}: {
  preview: ArtifactPreview;
  artifactId: string;
  sheetIdx: number;
  onSheet: (index: number) => void;
}) {
  const c = useClaudeTokens();
  const sheets = preview.workbook?.sheets ?? [];
  if (sheets.length === 0) {
    return <Typography sx={{ color: c.text.ghost, fontSize: '0.8rem' }}>No sheets found.</Typography>;
  }
  const active = Math.min(Math.max(sheetIdx, 0), sheets.length - 1);
  const sheet = sheets[active];
  const pick = (index: number) => {
    setSheetIndex(artifactId, index);
    onSheet(index);
  };
  return (
    <Box sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 1 }}>
      {sheets.length > 1 && (
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          {sheets.map((s, i) => (
            <Button
              key={s.name + i}
              size="small"
              variant={i === active ? 'contained' : 'text'}
              onClick={() => pick(i)}
              sx={{ textTransform: 'none', fontSize: '0.72rem', borderRadius: '6px', px: 1.25, py: 0.3, minWidth: 'auto' }}
            >
              {s.name}
            </Button>
          ))}
        </Box>
      )}
      <SheetTable rows={sheet.rows} />
      <Typography sx={{ color: c.text.ghost, fontSize: '0.68rem' }}>
        {sheet.total_rows} rows{sheets.length > 1 ? ` · ${sheet.name}` : ''}{sheet.truncated ? ' · truncated at 500 rows' : ''}
      </Typography>
    </Box>
  );
}

function DocumentPreview({ preview }: { preview: ArtifactPreview }) {
  const c = useClaudeTokens();
  const paragraphs = preview.document?.paragraphs ?? [];
  if (paragraphs.length === 0) {
    return <Typography sx={{ color: c.text.ghost, fontSize: '0.8rem' }}>No text found.</Typography>;
  }
  return (
    <Box sx={{ width: '100%', maxHeight: 600, overflow: 'auto', p: 3, bgcolor: '#fff', borderRadius: 1.5, color: '#1a1a1a' }}>
      {paragraphs.map((p, i) => (
        <Typography key={i} sx={{ fontSize: '0.85rem', lineHeight: 1.65, mb: 1.25, color: '#1a1a1a' }}>
          {p}
        </Typography>
      ))}
      {preview.document?.truncated && (
        <Typography sx={{ fontSize: '0.72rem', color: '#888' }}>… truncated at 500 paragraphs.</Typography>
      )}
    </Box>
  );
}

function SlidesPreview({
  preview, artifactId, slideIdx, onSlide,
}: {
  preview: ArtifactPreview;
  artifactId: string;
  slideIdx: number;
  onSlide: (index: number) => void;
}) {
  const c = useClaudeTokens();
  const slides = preview.slides ?? [];
  if (slides.length === 0) {
    return <Typography sx={{ color: c.text.ghost, fontSize: '0.8rem' }}>No slides found.</Typography>;
  }
  const active = Math.min(Math.max(slideIdx, 0), slides.length - 1);
  const slide = slides[active];
  const go = (index: number) => {
    const clamped = Math.min(Math.max(index, 0), slides.length - 1);
    setSlideIndex(artifactId, clamped);
    onSlide(clamped);
  };
  return (
    <Box sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ minHeight: 300, p: 3, bgcolor: '#fff', borderRadius: 1.5, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 1 }}>
        {slide.texts.length === 0 ? (
          <Typography sx={{ color: '#999', fontSize: '0.8rem' }}>(blank slide)</Typography>
        ) : (
          slide.texts.map((t, i) => (
            <Typography key={i} sx={{ color: '#1a1a1a', fontSize: i === 0 ? '1.3rem' : '0.9rem', fontWeight: i === 0 ? 700 : 400 }}>
              {t}
            </Typography>
          ))
        )}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Button size="small" disabled={active === 0} onClick={() => go(active - 1)}>‹ Prev</Button>
        <Typography sx={{ color: c.text.tertiary, fontSize: '0.74rem' }}>
          Slide {slide.index} of {slides.length}
        </Typography>
        <Button size="small" disabled={active === slides.length - 1} onClick={() => go(active + 1)}>Next ›</Button>
      </Box>
    </Box>
  );
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
  const [officePreview, setOfficePreview] = useState<ArtifactPreview | null>(null);
  const [officeLoading, setOfficeLoading] = useState(false);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfZoom, setPdfZoom] = useState('auto');
  const [sheetIdx, setSheetIdx] = useState(0);
  const [slideIdx, setSlideIdx] = useState(0);
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

  const selectedIsOffice = !!selected && isOfficePreview(selected.filename);

  useEffect(() => {
    if (!selected || !selectedIsOffice) {
      setOfficePreview(null);
      setOfficeLoading(false);
      return;
    }
    const controller = new AbortController();
    setOfficeLoading(true);
    fetchArtifactPreview(selected.id, controller.signal)
      .then((preview) => setOfficePreview(preview))
      .catch((reason) => {
        if (reason?.name !== 'AbortError') setOfficePreview({ kind: 'unsupported' });
      })
      .finally(() => {
        if (!controller.signal.aborted) setOfficeLoading(false);
      });
    return () => controller.abort();
  }, [selected, selectedIsOffice]);

  // Restore per-artifact view state (PDF page/zoom, sheet, slide) on selection.
  useEffect(() => {
    if (!selected) return;
    const pdf = getPdfView(selected.id);
    setPdfPage(pdf.page);
    setPdfZoom(pdf.zoom);
    setSheetIdx(getSheetIndex(selected.id, Number.MAX_SAFE_INTEGER));
    setSlideIdx(getSlideIndex(selected.id, Number.MAX_SAFE_INTEGER));
  }, [selectedId]);

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
                      <Box sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography sx={{ color: c.text.tertiary, fontSize: '0.72rem' }}>Page</Typography>
                          <InputBase
                            value={String(pdfPage)}
                            onChange={(e) => {
                              const next = Math.max(1, Math.floor(Number(e.target.value) || 1));
                              setPdfPage(next);
                              setPdfView(selected.id, next, pdfZoom);
                            }}
                            sx={{ width: 56, fontSize: '0.74rem', color: c.text.primary, bgcolor: c.bg.surface, borderRadius: 1, px: 1, py: 0.25, border: `1px solid ${c.border.subtle}`, '& input': { p: 0 } }}
                          />
                          <Typography sx={{ color: c.text.tertiary, fontSize: '0.72rem' }}>Zoom</Typography>
                          {PDF_ZOOMS.map((zoom) => (
                            <Button
                              key={zoom}
                              size="small"
                              variant={zoom === pdfZoom ? 'contained' : 'text'}
                              onClick={() => {
                                setPdfZoom(zoom);
                                setPdfView(selected.id, pdfPage, zoom);
                              }}
                              sx={{ textTransform: 'none', fontSize: '0.7rem', minWidth: 'auto', px: 1, py: 0.25, borderRadius: '6px' }}
                            >
                              {zoom === 'auto' ? 'Auto' : `${zoom}%`}
                            </Button>
                          ))}
                        </Box>
                        <Box component="iframe" title={selected.filename} src={`${contentUrl(selected)}${pdfFragment(pdfPage, pdfZoom)}`} sx={{ width: '100%', minHeight: 560, border: 0, borderRadius: 1.5, bgcolor: '#fff' }} />
                      </Box>
                    ) : selectedIsOffice ? (
                      officeLoading ? <Box sx={{ display: 'grid', placeItems: 'center', width: '100%' }}><CircularProgress size={24} /></Box>
                      : !officePreview || officePreview.kind === 'unsupported' ? (
                        <Box sx={{ display: 'grid', placeItems: 'center', textAlign: 'center', p: 4 }}>
                          <FolderOpenOutlinedIcon sx={{ fontSize: 44, color: c.text.ghost, mb: 1 }} />
                          <Typography sx={{ color: c.text.secondary, fontSize: '0.88rem' }}>Preview is not available for this file.</Typography>
                          <Button component="a" href={downloadUrl(selected)} download={selected.filename} size="small" startIcon={<DownloadOutlinedIcon />} sx={{ mt: 1.5 }}>Download file</Button>
                        </Box>
                      ) : officePreview.kind === 'workbook' ? (
                        <WorkbookPreview preview={officePreview} artifactId={selected.id} sheetIdx={sheetIdx} onSheet={setSheetIdx} />
                      ) : officePreview.kind === 'document' ? (
                        <DocumentPreview preview={officePreview} />
                      ) : (
                        <SlidesPreview preview={officePreview} artifactId={selected.id} slideIdx={slideIdx} onSlide={setSlideIdx} />
                      )
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
