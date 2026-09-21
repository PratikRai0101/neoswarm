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
    const handlers = new Map<string, (data: Record<string, unknown>) => Promise<void>>();
    mocks.dashboardWs.on.mockImplementation((event: string, callback: (data: Record<string, unknown>) => Promise<void>) => {
      handlers.set(event, callback);
      return vi.fn();
    });

    const cleanup = initBrowserCommandHandler();
    await handlers.get('browser:command')?.({
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
    const handlers = new Map<string, (data: Record<string, unknown>) => Promise<void>>();
    mocks.dashboardWs.on.mockImplementation((event: string, callback: (data: Record<string, unknown>) => Promise<void>) => {
      handlers.set(event, callback);
      return vi.fn();
    });

    const cleanup = initBrowserCommandHandler();
    await handlers.get('browser:command')?.({
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

  async function runTauriAction(data: Record<string, unknown>): Promise<void> {
    mocks.tauriBrowser.isTauriRuntime.mockReturnValue(true);
    const handlers = new Map<string, (data: Record<string, unknown>) => Promise<void>>();
    mocks.dashboardWs.on.mockImplementation((event: string, callback: (data: Record<string, unknown>) => Promise<void>) => {
      handlers.set(event, callback);
      return vi.fn();
    });

    const cleanup = initBrowserCommandHandler();
    await handlers.get('browser:command')?.(data);
    cleanup();
  }

  it('routes a Tauri click through browser_click with the webview label', async () => {
    mocks.core.invoke.mockResolvedValue({
      text: 'Clicked element: button',
      url: 'https://example.com',
      clickX: 0.25,
      clickY: 0.75,
    });

    await runTauriAction({
      request_id: 'click-1',
      action: 'click',
      browser_id: 'browser-1',
      tab_id: 'tab-1',
      params: { selector: '#submit' },
    });

    expect(mocks.core.invoke).toHaveBeenCalledWith('browser_click', {
      label: 'browser-1:tab-1',
      selector: '#submit',
    });
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'click-1',
      text: 'Clicked element: button',
      url: 'https://example.com',
      clickX: 0.25,
      clickY: 0.75,
    });
  });

  it('routes a Tauri type through browser_type with selector and text', async () => {
    mocks.core.invoke.mockResolvedValue({ text: 'Typed into: input', url: 'https://example.com' });

    await runTauriAction({
      request_id: 'type-1',
      action: 'type',
      browser_id: 'browser-1',
      tab_id: 'tab-1',
      params: { selector: '#search', text: 'hello world' },
    });

    expect(mocks.core.invoke).toHaveBeenCalledWith('browser_type', {
      label: 'browser-1:tab-1',
      selector: '#search',
      text: 'hello world',
    });
  });

  it('routes a Tauri scroll through browser_scroll with direction and amount', async () => {
    mocks.core.invoke.mockResolvedValue({
      text: 'Scrolled up by 250px',
      scrolled: 250,
      scrollTop: 0,
      scrollHeight: 2000,
      clientHeight: 600,
      atTop: true,
      atBottom: false,
      target: 'window',
      url: 'https://example.com',
    });

    await runTauriAction({
      request_id: 'scroll-1',
      action: 'scroll',
      browser_id: 'browser-1',
      tab_id: 'tab-1',
      params: { direction: 'up', amount: 250 },
    });

    expect(mocks.core.invoke).toHaveBeenCalledWith('browser_scroll', {
      label: 'browser-1:tab-1',
      direction: 'up',
      amount: 250,
    });
  });

  it('routes a Tauri screenshot through browser_screenshot', async () => {
    mocks.core.invoke.mockResolvedValue({ image: 'aGVsbG8=', url: 'https://example.com' });

    await runTauriAction({
      request_id: 'shot-1',
      action: 'screenshot',
      browser_id: 'browser-1',
      tab_id: 'tab-1',
      params: {},
    });

    expect(mocks.core.invoke).toHaveBeenCalledWith('browser_screenshot', { label: 'browser-1:tab-1' });
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'shot-1',
      image: 'aGVsbG8=',
      url: 'https://example.com',
    });
  });

  it('dispatches each Tauri batch item through the native command bridge', async () => {
    mocks.core.invoke.mockResolvedValue({ text: 'ok', url: 'https://example.com' });

    await runTauriAction({
      request_id: 'batch-1',
      action: 'batch',
      browser_id: 'browser-1',
      tab_id: 'tab-1',
      params: {
        actions: [
          { type: 'click', params: { selector: '#a' } },
          { type: 'type', params: { selector: '#q', text: 'hi' } },
        ],
      },
    });

    expect(mocks.core.invoke).toHaveBeenNthCalledWith(1, 'browser_click', {
      label: 'browser-1:tab-1',
      selector: '#a',
    });
    expect(mocks.core.invoke).toHaveBeenNthCalledWith(2, 'browser_type', {
      label: 'browser-1:tab-1',
      selector: '#q',
      text: 'hi',
    });
  });
});
