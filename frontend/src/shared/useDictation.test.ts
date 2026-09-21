import { describe, expect, it, vi } from 'vitest';

vi.mock('./config', () => ({ API_BASE: 'http://127.0.0.1:8324/api' }));

import { isDictationSupported, polishDictation } from './useDictation';

describe('dictation support probe', () => {
  it('reports unsupported where the API is missing', () => {
    expect(isDictationSupported()).toBe(false);
  });
});

describe('polishDictation', () => {
  it('returns the polished text on success', async () => {
    (globalThis.fetch as unknown) = vi.fn(async () => ({
      ok: true,
      json: async () => ({ text: 'Hello.', polished: true }),
    }));
    await expect(polishDictation('um hello')).resolves.toBe('Hello.');
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8324/api/voice/polish',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('falls back to raw text on HTTP errors', async () => {
    (globalThis.fetch as unknown) = vi.fn(async () => ({ ok: false }));
    await expect(polishDictation('raw words')).resolves.toBe('raw words');
  });

  it('falls back to raw text on network failure', async () => {
    (globalThis.fetch as unknown) = vi.fn(async () => {
      throw new Error('down');
    });
    await expect(polishDictation('raw words')).resolves.toBe('raw words');
  });

  it('falls back to raw text on empty model output', async () => {
    (globalThis.fetch as unknown) = vi.fn(async () => ({
      ok: true,
      json: async () => ({ text: '', polished: false }),
    }));
    await expect(polishDictation('raw words')).resolves.toBe('raw words');
  });
});
