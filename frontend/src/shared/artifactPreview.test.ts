import { describe, expect, it, vi } from 'vitest';

vi.mock('./config', () => ({ API_BASE: 'http://127.0.0.1:8324/api' }));

import {
  getPdfView,
  getSheetIndex,
  getSlideIndex,
  isOfficePreview,
  pdfFragment,
  setPdfView,
  setSheetIndex,
  setSlideIndex,
} from './artifactPreview';

describe('office detection', () => {
  it('matches office and csv suffixes only', () => {
    expect(isOfficePreview('report.xlsx')).toBe(true);
    expect(isOfficePreview('deck.PPTX')).toBe(true);
    expect(isOfficePreview('notes.docx')).toBe(true);
    expect(isOfficePreview('data.csv')).toBe(true);
    expect(isOfficePreview('data.tsv')).toBe(true);
    expect(isOfficePreview('paper.pdf')).toBe(false);
    expect(isOfficePreview('notes.txt')).toBe(false);
  });
});

describe('pdf view persistence', () => {
  it('round-trips page and zoom', () => {
    setPdfView('a1', 7, '125');
    expect(getPdfView('a1')).toEqual({ page: 7, zoom: '125' });
  });

  it('falls back to defaults on damaged entries', () => {
    expect(getPdfView('never-seen')).toEqual({ page: 1, zoom: 'auto' });
  });

  it('builds safe viewer fragments', () => {
    expect(pdfFragment(3, '100')).toBe('#page=3&zoom=100');
    expect(pdfFragment(0, '')).toBe('#page=1&zoom=auto');
    expect(pdfFragment(Number.NaN, 'auto')).toBe('#page=1&zoom=auto');
  });
});

describe('sheet and slide persistence', () => {
  it('clamps to the available range', () => {
    setSheetIndex('a1', 4);
    expect(getSheetIndex('a1', 2)).toBe(1);
    expect(getSheetIndex('a1', 10)).toBe(4);
    expect(getSheetIndex('missing', 3)).toBe(0);
    setSlideIndex('a1', 9);
    expect(getSlideIndex('a1', 3)).toBe(2);
  });
});
