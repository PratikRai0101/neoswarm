import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const created: Array<Record<string, any>> = [];
  const Webview = vi.fn(function (_window: unknown, label: string, options: Record<string, any>) {
    const listeners: Record<string, (event?: any) => void> = {};
    const native: Record<string, any> = {
      label,
      options,
      listeners,
      once: vi.fn((event: string, callback: (event?: any) => void) => {
        listeners[event] = callback;
        queueMicrotask(() => {
          if (event === 'tauri://created' && !label.includes('fail')) callback();
          if (event === 'tauri://error' && label.includes('fail')) callback({ payload: 'creation failed' });
        });
      }),
      close: vi.fn(async () => undefined),
      setPosition: vi.fn(async (position: unknown) => { native.position = position; }),
      setSize: vi.fn(async (size: unknown) => { native.size = size; }),
      show: vi.fn(async () => undefined),
      hide: vi.fn(async () => undefined),
    };
    created.push(native);
    return native;
  });
  return { created, Webview };
});

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }));
vi.mock('@tauri-apps/api/webview', () => ({
  getCurrentWebview: () => ({ window: {} }),
  Webview: mocks.Webview,
}));
vi.mock('@tauri-apps/api/dpi', () => ({
  LogicalPosition: class LogicalPosition { constructor(public x: number, public y: number) {} },
  LogicalSize: class LogicalSize { constructor(public width: number, public height: number) {} },
}));

import {
  removeAllTauriBrowserWebviews,
  removeTauriBrowserWebviews,
  syncTauriBrowserWebviews,
} from './tauriBrowser';

const tab = (id: string, url: string) => ({ id, url });

beforeEach(async () => {
  (globalThis as any).window = { __TAURI_INTERNALS__: {} };
  await removeAllTauriBrowserWebviews();
  mocks.created.length = 0;
  mocks.Webview.mockClear();
});

describe('Tauri browser webview lifecycle', () => {
  it('closes a native webview when creation fails', async () => {
    await expect(syncTauriBrowserWebviews(
      'browser-1',
      [tab('fail-tab', 'https://example.com')],
      'fail-tab',
      { x: 0, y: 0, width: 800, height: 600 },
    )).rejects.toBe('creation failed');

    expect(mocks.created).toHaveLength(1);
    expect(mocks.created[0].close).toHaveBeenCalledOnce();
  });

  it('creates one child per tab, reuses it, and closes removed tabs', async () => {
    await syncTauriBrowserWebviews(
      'browser-1',
      [tab('tab-1', 'https://example.com'), tab('tab-2', 'https://example.org')],
      'tab-1',
      { x: -10, y: 12, width: 800, height: 600 },
    );

    expect(mocks.Webview).toHaveBeenCalledTimes(2);
    expect(mocks.created[0].show).toHaveBeenCalledOnce();
    expect(mocks.created[1].hide).toHaveBeenCalledOnce();
    expect(mocks.created[0].position).toEqual({ x: 0, y: 12 });
    expect(mocks.created[0].size).toEqual({ width: 800, height: 600 });

    await syncTauriBrowserWebviews(
      'browser-1',
      [tab('tab-1', 'https://example.com')],
      'tab-1',
      { x: 20, y: 30, width: 500, height: 400 },
    );

    expect(mocks.Webview).toHaveBeenCalledTimes(2);
    expect(mocks.created[1].close).toHaveBeenCalledOnce();
    expect(mocks.created[0].position).toEqual({ x: 20, y: 30 });
    await removeTauriBrowserWebviews('browser-1');
    expect(mocks.created[0].close).toHaveBeenCalledOnce();
  });

  it('does not create duplicate children for concurrent syncs', async () => {
    await Promise.all([
      syncTauriBrowserWebviews('browser-1', [tab('tab-1', 'https://example.com')], 'tab-1', { x: 0, y: 0, width: 400, height: 300 }),
      syncTauriBrowserWebviews('browser-1', [tab('tab-1', 'https://example.com')], 'tab-1', { x: 0, y: 0, width: 400, height: 300 }),
    ]);

    expect(mocks.Webview).toHaveBeenCalledOnce();
  });
});
