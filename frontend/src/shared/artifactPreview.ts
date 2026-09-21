import { API_BASE } from './config';

// ---------------------------------------------------------------------------
// Artifact preview helpers: office-preview fetching plus per-artifact UI
// persistence (PDF page/zoom, workbook sheet, slide index). State lives in
// localStorage so it survives reloads; an in-memory fallback keeps SSR and
// the node test env working.
// ---------------------------------------------------------------------------

export interface PreviewSheet {
  name: string;
  rows: string[][];
  total_rows: number;
  truncated: boolean;
}

export interface ArtifactPreview {
  kind: 'workbook' | 'document' | 'slides' | 'unsupported';
  workbook?: { sheets: PreviewSheet[] };
  document?: { paragraphs: string[]; truncated: boolean };
  slides?: Array<{ index: number; texts: string[] }>;
  truncated?: boolean;
}

export function isOfficePreview(filename: string): boolean {
  const lower = filename.toLowerCase();
  return (
    lower.endsWith('.xlsx') ||
    lower.endsWith('.docx') ||
    lower.endsWith('.pptx') ||
    lower.endsWith('.csv') ||
    lower.endsWith('.tsv')
  );
}

export async function fetchArtifactPreview(
  artifactId: string,
  signal?: AbortSignal,
): Promise<ArtifactPreview> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/preview`, {
    signal,
  });
  if (!res.ok) throw new Error(`Preview failed: ${res.status}`);
  return (await res.json()) as ArtifactPreview;
}

const memoryStore = new Map<string, string>();

function storageGet(key: string): string | null {
  try {
    if (typeof localStorage !== 'undefined') return localStorage.getItem(key);
  } catch {
    // Private mode / SSR: fall through to memory.
  }
  return memoryStore.has(key) ? memoryStore.get(key)! : null;
}

function storageSet(key: string, value: string): void {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(key, value);
      return;
    }
  } catch {
    // Private mode / SSR: fall through to memory.
  }
  memoryStore.set(key, value);
}

function viewKey(artifactId: string, field: string): string {
  return `neoswarm:artifact:${artifactId}:${field}`;
}

export function getPdfView(artifactId: string): { page: number; zoom: string } {
  let page = 1;
  let zoom = 'auto';
  try {
    const raw = storageGet(viewKey(artifactId, 'pdf'));
    if (raw) {
      const parsed = JSON.parse(raw) as { page?: unknown; zoom?: unknown };
      if (typeof parsed.page === 'number' && Number.isFinite(parsed.page) && parsed.page >= 1) {
        page = Math.floor(parsed.page);
      }
      if (typeof parsed.zoom === 'string' && parsed.zoom) zoom = parsed.zoom;
    }
  } catch {
    // Damaged entry: defaults win.
  }
  return { page, zoom };
}

export function setPdfView(artifactId: string, page: number, zoom: string): void {
  storageSet(viewKey(artifactId, 'pdf'), JSON.stringify({ page, zoom }));
}

export function pdfFragment(page: number, zoom: string): string {
  const safePage = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1;
  return `#page=${safePage}&zoom=${encodeURIComponent(zoom || 'auto')}`;
}

export function getSheetIndex(artifactId: string, sheetCount: number): number {
  const raw = storageGet(viewKey(artifactId, 'sheet'));
  const index = raw == null ? 0 : Number.parseInt(raw, 10);
  if (!Number.isFinite(index) || index < 0) return 0;
  return sheetCount > 0 ? Math.min(index, sheetCount - 1) : 0;
}

export function setSheetIndex(artifactId: string, index: number): void {
  storageSet(viewKey(artifactId, 'sheet'), String(index));
}

export function getSlideIndex(artifactId: string, slideCount: number): number {
  const raw = storageGet(viewKey(artifactId, 'slide'));
  const index = raw == null ? 0 : Number.parseInt(raw, 10);
  if (!Number.isFinite(index) || index < 0) return 0;
  return slideCount > 0 ? Math.min(index, slideCount - 1) : 0;
}

export function setSlideIndex(artifactId: string, index: number): void {
  storageSet(viewKey(artifactId, 'slide'), String(index));
}
