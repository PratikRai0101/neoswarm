import { getVersion } from '@tauri-apps/api/app';
import { relaunch } from '@tauri-apps/plugin-process';
import { check, Update, DownloadEvent } from '@tauri-apps/plugin-updater';
import { isTauriRuntime } from './tauriBrowser';

interface UpdateSnapshot {
  status: string;
  info: NeoSwarmUpdateInfo | null;
  error: string | null;
}

type UpdateListener<T> = (value: T) => void;

const NO_UPDATE_KEY = 'neoswarm:no-update';

/** Opt-out escape hatch (mirrors OPENSWARM_NO_UPDATE=1): skips all checks. */
export function isUpdateCheckSkipped(): boolean {
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem(NO_UPDATE_KEY) === '1') {
      return true;
    }
  } catch {
    // Storage unavailable: updates stay enabled.
  }
  return false;
}

export function setUpdateCheckSkipped(skipped: boolean): void {
  try {
    if (typeof localStorage !== 'undefined') {
      if (skipped) localStorage.setItem(NO_UPDATE_KEY, '1');
      else localStorage.removeItem(NO_UPDATE_KEY);
    }
  } catch {
    // Storage unavailable: ignore.
  }
}

function splitVersion(version: string): { nums: number[]; tag: string } {
  const clean = version.trim().replace(/^v/i, '');
  const [core, ...rest] = clean.split('-');
  return {
    nums: core.split('.').map((part) => {
      const num = parseInt(part, 10);
      return Number.isFinite(num) ? num : 0;
    }),
    tag: rest.join('-'),
  };
}

/** Numeric-aware version compare; a release outranks its own prereleases. */
export function compareVersions(a: string, b: string): number {
  const left = splitVersion(a);
  const right = splitVersion(b);
  const width = Math.max(left.nums.length, right.nums.length);
  for (let i = 0; i < width; i += 1) {
    const diff = (left.nums[i] ?? 0) - (right.nums[i] ?? 0);
    if (diff !== 0) return diff > 0 ? 1 : -1;
  }
  if (left.tag === right.tag) return 0;
  if (!left.tag) return 1;
  if (!right.tag) return -1;
  return left.tag < right.tag ? -1 : 1;
}

/** Never self-downgrade: only strictly newer versions count as available. */
export function isNewerVersion(current: string, candidate: string): boolean {
  if (!current || !candidate) return true;
  return compareVersions(candidate, current) > 0;
}

let singleton: NeoSwarmAPI | null = null;
let pendingUpdate: Update | null = null;
let snapshot: UpdateSnapshot = { status: 'idle', info: null, error: null };
const availableListeners = new Set<UpdateListener<NeoSwarmUpdateInfo>>();
const notAvailableListeners = new Set<UpdateListener<NeoSwarmUpdateInfo>>();
const progressListeners = new Set<UpdateListener<NeoSwarmDownloadProgress>>();
const downloadedListeners = new Set<UpdateListener<NeoSwarmUpdateInfo>>();
const errorListeners = new Set<UpdateListener<string>>();

function infoFor(update: Update): NeoSwarmUpdateInfo {
  return {
    version: update.version,
    releaseDate: update.date,
    releaseNotes: update.body,
  };
}

function emitError(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  snapshot = { ...snapshot, status: 'error', error: message };
  errorListeners.forEach((listener) => listener(message));
}

function setDownloaded(): void {
  const info = snapshot.info || (pendingUpdate ? infoFor(pendingUpdate) : { version: '' });
  snapshot = { status: 'downloaded', info, error: null };
  downloadedListeners.forEach((listener) => listener(info));
}

async function checkForUpdates(): Promise<{ success: boolean; version?: string; error?: string }> {
  try {
    if (isUpdateCheckSkipped()) {
      return { success: false, error: 'Update checks are disabled' };
    }
    const update = await check();
    pendingUpdate = update;
    if (!update) {
      snapshot = { status: 'not-available', info: null, error: null };
      notAvailableListeners.forEach((listener) => listener({ version: '' }));
      return { success: true };
    }

    let current = '';
    try {
      current = await getVersion();
    } catch {
      // Unknown current version: trust the feed.
    }
    if (!isNewerVersion(current, update.version)) {
      pendingUpdate = null;
      snapshot = { status: 'not-available', info: null, error: null };
      notAvailableListeners.forEach((listener) => listener({ version: '' }));
      return { success: true };
    }

    const info = infoFor(update);
    snapshot = { status: 'available', info, error: null };
    availableListeners.forEach((listener) => listener(info));
    return { success: true, version: update.version };
  } catch (error) {
    emitError(error);
    return { success: false, error: error instanceof Error ? error.message : String(error) };
  }
}

function handleDownloadEvent(event: DownloadEvent, total: { value: number }, transferred: { value: number }): void {
  if (event.event === 'Started') {
    total.value = event.data.contentLength || 0;
    transferred.value = 0;
  } else if (event.event === 'Progress') {
    transferred.value += event.data.chunkLength || 0;
  }

  const percent = total.value > 0 ? (transferred.value / total.value) * 100 : 0;
  const progress = {
    bytesPerSecond: 0,
    percent: Math.min(99.9, percent),
    transferred: transferred.value,
    total: total.value,
  };
  snapshot = { ...snapshot, status: 'downloading', error: null };
  progressListeners.forEach((listener) => listener(progress));
}

async function downloadUpdate(): Promise<{ success: boolean; error?: string }> {
  try {
    if (!pendingUpdate) {
      const result = await checkForUpdates();
      if (!result.success || !pendingUpdate) return result;
    }
    const total = { value: 0 };
    const transferred = { value: 0 };
    await pendingUpdate!.download((event) => handleDownloadEvent(event, total, transferred));
    setDownloaded();
    return { success: true };
  } catch (error) {
    emitError(error);
    return { success: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function installUpdate(): Promise<void> {
  try {
    if (!pendingUpdate) throw new Error('No downloaded update is available');
    await pendingUpdate.install();
    await relaunch();
  } catch (error) {
    emitError(error);
  }
}

function subscribe<T>(listeners: Set<UpdateListener<T>>, listener: UpdateListener<T>): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Return the update API used by the existing settings surface in Tauri. */
export function getTauriUpdater(): NeoSwarmAPI | undefined {
  if (!isTauriRuntime()) return undefined;
  if (singleton) return singleton;

  singleton = {
    getBackendPort: () => window.__NEOSWARM_PORT__ || 8324,
    getWebviewPreloadPath: () => '',
    getAppVersion: () => getVersion(),
    getUpdateStatus: async () => snapshot,
    checkForUpdates,
    downloadUpdate,
    installUpdate,
    onUpdateAvailable: (listener) => subscribe(availableListeners, listener),
    onUpdateNotAvailable: (listener) => subscribe(notAvailableListeners, listener),
    onDownloadProgress: (listener) => subscribe(progressListeners, listener),
    onUpdateDownloaded: (listener) => subscribe(downloadedListeners, listener),
    onUpdateError: (listener) => subscribe(errorListeners, listener),
    onWebviewNewWindow: () => () => undefined,
  };
  return singleton;
}
