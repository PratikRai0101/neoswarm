import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const dashboardWs = {
    on: vi.fn(),
    send: vi.fn(),
  };
  const browserRegistry = {
    getWebview: vi.fn(),
    getActiveTabId: vi.fn(),
  };
  const tauriBrowser = {
    isTauriRuntime: vi.fn(() => false),
    tauriBrowserLabel: (browserId: string, tabId: string) => `${browserId}:${tabId}`,
  };
  const core = { invoke: vi.fn() };
  return { dashboardWs, browserRegistry, tauriBrowser, core };
});

vi.mock('./ws/WebSocketManager', () => ({ dashboardWs: mocks.dashboardWs }));
vi.mock('./browserRegistry', () => mocks.browserRegistry);
vi.mock('./tauriBrowser', () => mocks.tauriBrowser);
vi.mock('@tauri-apps/api/core', () => mocks.core);

import { getActivity, initBrowserCommandHandler } from './browserCommandHandler';

describe('browser command bridge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.browserRegistry.getWebview.mockReturnValue(undefined);
    mocks.browserRegistry.getActiveTabId.mockReturnValue('tab-1');
    mocks.tauriBrowser.isTauriRuntime.mockReturnValue(false);
  });

  it('clears activity when a command targets a missing browser webview', async () => {
    let handler: ((data: Record<string, unknown>) => Promise<void>) | undefined;
    mocks.dashboardWs.on.mockImplementation((_event: string, callback: typeof handler) => {
      handler = callback;
      return vi.fn();
    });

    const cleanup = initBrowserCommandHandler();
    await handler?.({
      request_id: 'request-1',
      action: 'get_text',
      browser_id: 'missing-browser',
      tab_id: 'tab-1',
      params: {},
    });

    expect(getActivity('missing-browser')).toBeNull();
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'request-1',
      error: "Browser card 'missing-browser' tab 'tab-1' not found or not an Electron webview",
    });
    cleanup();
  });

  it('routes Tauri navigation through the native command bridge', async () => {
    mocks.tauriBrowser.isTauriRuntime.mockReturnValue(true);
    mocks.core.invoke.mockResolvedValue(undefined);
    let handler: ((data: Record<string, unknown>) => Promise<void>) | undefined;
    mocks.dashboardWs.on.mockImplementation((_event: string, callback: typeof handler) => {
      handler = callback;
      return vi.fn();
    });

    const cleanup = initBrowserCommandHandler();
    await handler?.({
      request_id: 'request-2',
      action: 'navigate',
      browser_id: 'browser-1',
      tab_id: 'tab-1',
      params: { url: 'example.com' },
    });

    expect(mocks.core.invoke).toHaveBeenCalledWith('browser_navigate', {
      label: 'browser-1:tab-1',
      url: 'https://example.com',
    });
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'request-2',
      text: 'Navigated to https://example.com',
      url: 'https://example.com',
    });
    cleanup();
  });
});
