import { getCurrentWebview, Webview } from '@tauri-apps/api/webview';
import { LogicalPosition, LogicalSize } from '@tauri-apps/api/dpi';

export interface TauriBrowserRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TauriBrowserTab {
  id: string;
  url: string;
}

interface ManagedWebview {
  webview: Webview;
  url: string;
  creating: Promise<void>;
}

const managed = new Map<string, ManagedWebview>();

export function isTauriRuntime(): boolean {
  return Boolean((window as any).__TAURI_INTERNALS__);
}

function key(browserId: string, tabId: string): string {
  return `${browserId}:${tabId}`;
}

function label(browserId: string, tabId: string): string {
  return `browser-${browserId}-${tabId}`.replace(/[^a-zA-Z0-9/_:-]/g, '-');
}

function clampRect(rect: TauriBrowserRect): TauriBrowserRect {
  return {
    x: Math.max(0, Math.round(rect.x)),
    y: Math.max(0, Math.round(rect.y)),
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
  };
}

async function closeManaged(entry: ManagedWebview | undefined): Promise<void> {
  if (!entry) return;
  try {
    await entry.creating;
  } catch {
    // Creation errors are reported by the caller; cleanup is best effort.
  }
  try {
    await entry.webview.close();
  } catch {
    // The native webview may already have been removed with its parent window.
  }
}

async function createManaged(
  browserId: string,
  tab: TauriBrowserTab,
  rect: TauriBrowserRect,
): Promise<ManagedWebview> {
  const current = getCurrentWebview();
  const native = new Webview(current.window, label(browserId, tab.id), {
    url: tab.url,
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
    focus: false,
    dragDropEnabled: true,
  });

  let resolveCreation!: () => void;
  let rejectCreation!: (reason?: unknown) => void;
  const creating = new Promise<void>((resolve, reject) => {
    resolveCreation = resolve;
    rejectCreation = reject;
  });
  native.once('tauri://created', () => resolveCreation());
  native.once('tauri://error', (event) => rejectCreation(event.payload));

  const entry = { webview: native, url: tab.url, creating };
  managed.set(key(browserId, tab.id), entry);
  await creating;
  return entry;
}

async function syncTab(
  browserId: string,
  tab: TauriBrowserTab,
  activeTabId: string,
  rect: TauriBrowserRect,
): Promise<void> {
  const tabKey = key(browserId, tab.id);
  let entry = managed.get(tabKey);

  if (!entry || entry.url !== tab.url) {
    if (entry) {
      managed.delete(tabKey);
      await closeManaged(entry);
    }
    try {
      entry = await createManaged(browserId, tab, rect);
    } catch (error) {
      managed.delete(tabKey);
      throw error;
    }
  }

  const current = managed.get(tabKey);
  if (!current || current !== entry) return;

  await current.webview.setPosition(new LogicalPosition(rect.x, rect.y));
  await current.webview.setSize(new LogicalSize(rect.width, rect.height));
  if (tab.id === activeTabId) {
    await current.webview.show();
  } else {
    await current.webview.hide();
  }
}

/**
 * Keep native child webviews aligned with a browser card's body.
 *
 * Tauri's Webview API intentionally exposes positioning and lifecycle, but not
 * Electron's DOM/evaluation methods. This module therefore owns only the
 * native visual surface; browser command execution remains a separate seam.
 */
export async function syncTauriBrowserWebviews(
  browserId: string,
  tabs: TauriBrowserTab[],
  activeTabId: string,
  rect: TauriBrowserRect,
): Promise<void> {
  if (!isTauriRuntime()) return;
  const normalized = clampRect(rect);
  const liveKeys = new Set(tabs.map((tab) => key(browserId, tab.id)));

  for (const [tabKey, entry] of managed) {
    if (tabKey.startsWith(`${browserId}:`) && !liveKeys.has(tabKey)) {
      managed.delete(tabKey);
      await closeManaged(entry);
    }
  }

  const results = await Promise.allSettled(
    tabs.map((tab) => syncTab(browserId, tab, activeTabId, normalized)),
  );
  const failure = results.find((result): result is PromiseRejectedResult => result.status === 'rejected');
  if (failure) throw failure.reason;
}

export async function removeTauriBrowserWebviews(browserId: string): Promise<void> {
  const removals: Promise<void>[] = [];
  for (const [tabKey, entry] of managed) {
    if (!tabKey.startsWith(`${browserId}:`)) continue;
    managed.delete(tabKey);
    removals.push(closeManaged(entry));
  }
  await Promise.allSettled(removals);
}

export async function removeAllTauriBrowserWebviews(): Promise<void> {
  const removals = Array.from(managed.values()).map(closeManaged);
  managed.clear();
  await Promise.allSettled(removals);
}
