import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const dashboardWs = { on: vi.fn(), send: vi.fn() };
  const browserRegistry = {
    getWebview: vi.fn(),
    getActiveTabId: vi.fn(),
    setPopupOpener: vi.fn(),
    getPopupOpener: vi.fn(),
    clearPopupOpener: vi.fn(),
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
vi.mock('./browserControl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./browserControl')>();
  return actual;
});

import { initBrowserCommandHandler } from './browserCommandHandler';
import { isBrowserControlled, setBrowserControlled } from './browserControl';

type Handler = (data: Record<string, unknown>) => Promise<void>;

function captureHandlers(): Map<string, Handler> {
  const handlers = new Map<string, Handler>();
  mocks.dashboardWs.on.mockImplementation((event: string, callback: Handler) => {
    handlers.set(event, callback);
    return vi.fn();
  });
  return handlers;
}

describe('browser takeover guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.browserRegistry.getActiveTabId.mockReturnValue('tab-1');
    mocks.tauriBrowser.isTauriRuntime.mockReturnValue(false);
    setBrowserControlled('b1', false);
  });

  it('fails fast when the browser is user-controlled', async () => {
    const handlers = captureHandlers();
    const cleanup = initBrowserCommandHandler();
    setBrowserControlled('b1', true);

    await handlers.get('browser:command')?.({
      request_id: 'takeover-1',
      action: 'click',
      browser_id: 'b1',
      tab_id: 'tab-1',
      params: { selector: '#x' },
    });

    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'takeover-1',
      error: "Browser 'b1' is under user control. Ask the user to return it to the agent, or wait for them to finish.",
    });
    expect(mocks.browserRegistry.getWebview).not.toHaveBeenCalled();
    setBrowserControlled('b1', false);
    cleanup();
  });

  it('syncs control state from browser:control_changed', async () => {
    const handlers = captureHandlers();
    const cleanup = initBrowserCommandHandler();

    await handlers.get('browser:control_changed')?.({ browser_id: 'b9', controlled: true });
    expect(isBrowserControlled('b9')).toBe(true);
    await handlers.get('browser:control_changed')?.({ browser_id: 'b9', controlled: false });
    expect(isBrowserControlled('b9')).toBe(false);
    cleanup();
  });
});

describe('browser hover dispatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.browserRegistry.getActiveTabId.mockReturnValue('tab-1');
    mocks.tauriBrowser.isTauriRuntime.mockReturnValue(true);
    setBrowserControlled('b1', false);
  });

  it('routes hover through the native browser_hover command', async () => {
    mocks.core.invoke.mockResolvedValue({
      text: 'Hovered element: div',
      url: 'https://example.com',
      hoverX: 10,
      hoverY: 20,
    });
    const handlers = captureHandlers();
    const cleanup = initBrowserCommandHandler();

    await handlers.get('browser:command')?.({
      request_id: 'hover-1',
      action: 'hover',
      browser_id: 'b1',
      tab_id: 'tab-1',
      params: { selector: '.menu' },
    });

    expect(mocks.core.invoke).toHaveBeenCalledWith('browser_hover', {
      label: 'b1:tab-1',
      selector: '.menu',
    });
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'hover-1',
      text: 'Hovered element: div',
      url: 'https://example.com',
      hoverX: 10,
      hoverY: 20,
    });
    cleanup();
  });

  it('rejects hover without a selector', async () => {
    const handlers = captureHandlers();
    const cleanup = initBrowserCommandHandler();

    await handlers.get('browser:command')?.({
      request_id: 'hover-2',
      action: 'hover',
      browser_id: 'b1',
      tab_id: 'tab-1',
      params: {},
    });

    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:result', {
      request_id: 'hover-2',
      error: 'selector parameter is required',
    });
    cleanup();
  });
});
