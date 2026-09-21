import { describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  check: vi.fn(),
  getVersion: vi.fn(),
  relaunch: vi.fn(),
  isTauriRuntime: vi.fn(() => true),
}));

vi.mock('@tauri-apps/plugin-updater', () => ({ check: mocks.check }));
vi.mock('@tauri-apps/api/app', () => ({ getVersion: mocks.getVersion }));
vi.mock('@tauri-apps/plugin-process', () => ({ relaunch: mocks.relaunch }));
vi.mock('./tauriBrowser', () => ({ isTauriRuntime: mocks.isTauriRuntime }));

import { getTauriUpdater } from './tauriUpdater';

describe('Tauri updater lifecycle', () => {
  it('checks, downloads, reports progress, and installs an update', async () => {
    (globalThis as any).window = { __TAURI_INTERNALS__: {}, __NEOSWARM_PORT__: 8324 };
    mocks.getVersion.mockResolvedValue('0.1.0');
    mocks.relaunch.mockResolvedValue(undefined);
    const update = {
      version: '0.2.0',
      date: '2026-08-04T00:00:00Z',
      body: 'Browser reliability improvements',
      download: vi.fn(async (callback: (event: any) => void) => {
        callback({ event: 'Started', data: { contentLength: 100 } });
        callback({ event: 'Progress', data: { chunkLength: 40 } });
        callback({ event: 'Progress', data: { chunkLength: 60 } });
      }),
      install: vi.fn(async () => undefined),
    };
    mocks.check.mockResolvedValue(update);

    const api = getTauriUpdater();
    expect(api).toBeDefined();
    expect(api?.getBackendPort?.()).toBe(8324);

    const available = vi.fn();
    const progress = vi.fn();
    const downloaded = vi.fn();
    api?.onUpdateAvailable?.(available);
    api?.onDownloadProgress?.(progress);
    api?.onUpdateDownloaded?.(downloaded);

    await expect(api?.checkForUpdates?.()).resolves.toEqual({ success: true, version: '0.2.0' });
    expect(available).toHaveBeenCalledWith({
      version: '0.2.0',
      releaseDate: '2026-08-04T00:00:00Z',
      releaseNotes: 'Browser reliability improvements',
    });

    await expect(api?.downloadUpdate?.()).resolves.toEqual({ success: true });
    expect(update.download).toHaveBeenCalledOnce();
    expect(progress.mock.calls.map(([value]) => value.percent)).toEqual([0, 40, 99.9]);
    expect(downloaded).toHaveBeenCalledWith({
      version: '0.2.0',
      releaseDate: '2026-08-04T00:00:00Z',
      releaseNotes: 'Browser reliability improvements',
    });

    await api?.installUpdate?.();
    expect(update.install).toHaveBeenCalledOnce();
    expect(mocks.relaunch).toHaveBeenCalledOnce();
  });

  it('turns provider failures into an actionable API result', async () => {
    const error = new Error('signature verification failed');
    mocks.check.mockRejectedValue(error);

    // The singleton is already initialized by the first test, so this uses the
    // same public API while exercising a subsequent check failure.
    const api = getTauriUpdater();
    const errors = vi.fn();
    api?.onUpdateError?.(errors);

    await expect(api?.checkForUpdates?.()).resolves.toEqual({
      success: false,
      error: 'signature verification failed',
    });
    expect(errors).toHaveBeenCalledWith('signature verification failed');
    await expect(api?.getUpdateStatus?.()).resolves.toMatchObject({
      status: 'error',
      error: 'signature verification failed',
    });
  });

  it('never self-downgrades to an older or equal version', async () => {
    mocks.getVersion.mockResolvedValue('1.7.11');
    mocks.check.mockResolvedValue({
      version: '1.7.10',
      date: '2026-08-04T00:00:00Z',
      body: 'older',
      download: vi.fn(),
      install: vi.fn(),
    });
    const api = getTauriUpdater();
    const notAvailable = vi.fn();
    api?.onUpdateNotAvailable?.(notAvailable);
    await expect(api?.checkForUpdates?.()).resolves.toEqual({ success: true });
    expect(notAvailable).toHaveBeenCalled();
  });

  it('treats prereleases as older than their release', async () => {
    mocks.getVersion.mockResolvedValue('1.8.0');
    mocks.check.mockResolvedValue({
      version: '1.8.0-exp.1',
      date: '2026-09-18T00:00:00Z',
      body: 'experimental',
      download: vi.fn(),
      install: vi.fn(),
    });
    const api = getTauriUpdater();
    await expect(api?.checkForUpdates?.()).resolves.toEqual({ success: true });
    await expect(api?.getUpdateStatus?.()).resolves.toMatchObject({ status: 'not-available' });
  });

  it('supports an opt-out escape hatch', async () => {
    const { isUpdateCheckSkipped, setUpdateCheckSkipped } = await import('./tauriUpdater');
    const store = new Map<string, string>();
    (globalThis as any).localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v); },
      removeItem: (k: string) => { store.delete(k); },
    };
    try {
      expect(isUpdateCheckSkipped()).toBe(false);
      setUpdateCheckSkipped(true);
      expect(isUpdateCheckSkipped()).toBe(true);
      const api = getTauriUpdater();
      await expect(api?.checkForUpdates?.()).resolves.toEqual({
        success: false,
        error: 'Update checks are disabled',
      });
      setUpdateCheckSkipped(false);
      expect(isUpdateCheckSkipped()).toBe(false);
    } finally {
      delete (globalThis as any).localStorage;
    }
  });
});

describe('update version compare', () => {
  it('orders releases numerically, not lexicographically', async () => {
    const { compareVersions, isNewerVersion } = await import('./tauriUpdater');
    expect(compareVersions('1.7.9', '1.7.11')).toBe(-1);
    expect(compareVersions('1.7.11', '1.7.11')).toBe(0);
    expect(compareVersions('1.8.0', '1.7.11')).toBe(1);
    expect(compareVersions('v1.7.11', '1.7.11')).toBe(0);
    expect(isNewerVersion('1.7.11', '1.8.0-exp.1')).toBe(true);
    expect(isNewerVersion('1.8.0', '1.8.0-exp.1')).toBe(false);
  });
});
