import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const dashboardWs = { on: vi.fn(), send: vi.fn() };
  const browserRegistry = { getWebview: vi.fn() };
  const tauriBrowser = {
    isTauriRuntime: vi.fn(() => false),
    tauriBrowserLabel: (browserId: string, tabId: string) => `${browserId}:${tabId}`,
    focusTauriBrowser: vi.fn(async () => {}),
  };
  return { dashboardWs, browserRegistry, tauriBrowser };
});

vi.mock('./ws/WebSocketManager', () => ({ dashboardWs: mocks.dashboardWs }));
vi.mock('./browserRegistry', () => mocks.browserRegistry);
vi.mock('./tauriBrowser', () => mocks.tauriBrowser);

import {
  isBrowserControlled,
  setBrowserControlled,
  subscribeBrowserControl,
  takeBrowserControl,
  releaseBrowserControl,
  POPUP_HOOK_SCRIPT,
  POPUP_POLL_SCRIPT,
} from './browserControl';

describe('browser takeover state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setBrowserControlled('b1', false);
    setBrowserControlled('b2', false);
  });

  it('tracks control state and notifies subscribers', () => {
    const seen: Array<[string, boolean]> = [];
    const unsub = subscribeBrowserControl((id, state) => seen.push([id, state]));
    expect(isBrowserControlled('b1')).toBe(false);
    setBrowserControlled('b1', true);
    expect(isBrowserControlled('b1')).toBe(true);
    setBrowserControlled('b1', false);
    expect(seen).toEqual([['b1', true], ['b1', false]]);
    unsub();
  });

  it('take sends take_control and focuses the page', () => {
    takeBrowserControl('b1');
    expect(isBrowserControlled('b1')).toBe(true);
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:take_control', {
      browser_id: 'b1',
    });
  });

  it('release sends release_control and clears state', () => {
    takeBrowserControl('b1');
    releaseBrowserControl('b1');
    expect(isBrowserControlled('b1')).toBe(false);
    expect(mocks.dashboardWs.send).toHaveBeenCalledWith('browser:release_control', {
      browser_id: 'b1',
    });
  });
});

describe('popup hook script', () => {
  const stash = { window: (globalThis as any).window, location: (globalThis as any).location };
  beforeEach(() => {
    delete (globalThis as any).window;
    delete (globalThis as any).location;
  });

  function installHook() {
    const opened: string[] = [];
    (globalThis as any).window = {
      __neoswarmPopupHook: undefined,
      __neoswarmPendingPopup: undefined,
      open: (...args: unknown[]) => {
        opened.push(String(args[0]));
        return 'native-window';
      },
    };
    (globalThis as any).location = { href: 'https://opener.example/' };
    // eslint-disable-next-line no-eval
    const result = eval(POPUP_HOOK_SCRIPT);
    return { opened, result };
  }

  it('captures window.open targets instead of opening them', () => {
    const { opened, result } = installHook();
    expect(result).toBe('popup-hook-installed');
    const ret = (globalThis as any).window.open('https://popup.example/', '_blank');
    expect(ret).toBeNull();
    expect(opened).toEqual([]);
    expect((globalThis as any).window.__neoswarmPendingPopup.url).toBe('https://popup.example/');
    expect((globalThis as any).window.__neoswarmPendingPopup.opener).toBe('https://opener.example/');
  });

  it('passes about:blank through to the native open', () => {
    const { opened } = installHook();
    const ret = (globalThis as any).window.open('about:blank', '_blank');
    expect(ret).toBe('native-window');
    expect(opened).toEqual(['about:blank']);
  });

  it('poll script drains the pending popup exactly once', () => {
    installHook();
    (globalThis as any).window.open('https://popup.example/', '_blank');
    // eslint-disable-next-line no-eval
    const first = eval(POPUP_POLL_SCRIPT);
    expect(JSON.parse(first).url).toBe('https://popup.example/');
    // eslint-disable-next-line no-eval
    expect(eval(POPUP_POLL_SCRIPT)).toBe('none');
  });

  it('re-install is a no-op', () => {
    installHook();
    // eslint-disable-next-line no-eval
    expect(eval(POPUP_HOOK_SCRIPT)).toBe('already-hooked');
  });

  afterEach(() => {
    (globalThis as any).window = stash.window;
    (globalThis as any).location = stash.location;
  });
});
