import { useEffect, useState } from 'react';
import { dashboardWs } from './ws/WebSocketManager';
import { getWebview } from './browserRegistry';
import { focusTauriBrowser, isTauriRuntime } from './tauriBrowser';

// ---------------------------------------------------------------------------
// User-takeover state for browser cards.
//
// While a browser is user-controlled, agent commands to it fail fast
// (backend guard in send_browser_command + local guard in the command
// handler). Taking control focuses the page webview so the user's keyboard
// goes straight to the page; returning hands it back to the agent.
// State syncs across clients via the browser:control_changed event.
// ---------------------------------------------------------------------------

const controlled = new Set<string>();

type ControlListener = (browserId: string, isControlled: boolean) => void;
const listeners = new Set<ControlListener>();

function notify(browserId: string) {
  const state = controlled.has(browserId);
  listeners.forEach((fn) => fn(browserId, state));
}

export function isBrowserControlled(browserId: string): boolean {
  return controlled.has(browserId);
}

export function setBrowserControlled(browserId: string, state: boolean): void {
  if (state) {
    if (controlled.has(browserId)) return;
    controlled.add(browserId);
  } else {
    if (!controlled.has(browserId)) return;
    controlled.delete(browserId);
  }
  notify(browserId);
}

export function subscribeBrowserControl(fn: ControlListener): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

async function focusPage(browserId: string): Promise<void> {
  try {
    if (isTauriRuntime()) {
      await focusTauriBrowser(browserId);
    } else {
      getWebview(browserId)?.focus?.();
    }
  } catch {
    // Focusing is best effort; control still transfers.
  }
}

export function takeBrowserControl(browserId: string): void {
  if (!browserId) return;
  setBrowserControlled(browserId, true);
  dashboardWs.send('browser:take_control', { browser_id: browserId });
  void focusPage(browserId);
}

export function releaseBrowserControl(browserId: string): void {
  if (!browserId) return;
  setBrowserControlled(browserId, false);
  dashboardWs.send('browser:release_control', { browser_id: browserId });
}

export function useBrowserControl(browserId: string): boolean {
  const [state, setState] = useState(() => isBrowserControlled(browserId));
  useEffect(() => {
    setState(isBrowserControlled(browserId));
    return subscribeBrowserControl((changedId, next) => {
      if (changedId === browserId) setState(next);
    });
  }, [browserId]);
  return state;
}

// ---------------------------------------------------------------------------
// Popup identity.
//
// window.open targets keep their own page identity: on Electron they open as
// a new card tab (wired via the webview new-window event); on Tauri the
// popup hook below routes them to a new card tab too. Closing a popup tab
// returns to its opener (see BrowserCard handleCloseTab).
// ---------------------------------------------------------------------------

export const POPUP_HOOK_SCRIPT = `(() => {
  try {
    if (window.__neoswarmPopupHook) return 'already-hooked';
    window.__neoswarmPopupHook = true;
    window.__neoswarmPendingPopup = null;
    const rawOpen = window.open.bind(window);
    window.open = function (url, target, features) {
      try {
        const resolved = String(url || '');
        if (resolved && resolved !== 'about:blank') {
          window.__neoswarmPendingPopup = { opener: location.href, url: resolved, at: Date.now() };
          return null;
        }
      } catch (e) { /* fall through to native open */ }
      return rawOpen(url, target, features);
    };
    return 'popup-hook-installed';
  } catch (error) {
    return 'popup-hook-failed: ' + String(error);
  }
})()`;

export const POPUP_POLL_SCRIPT = `(() => {
  try {
    const pending = window.__neoswarmPendingPopup || null;
    window.__neoswarmPendingPopup = null;
    return pending ? JSON.stringify(pending) : 'none';
  } catch (error) {
    return 'none';
  }
})()`;
