const port = (window as any).__NEOSWARM_PORT__ || 8324;
const isTauri = Boolean((window as any).__TAURI_INTERNALS__);
// Tauri serves the UI from tauri.localhost, while the backend deliberately
// binds only to loopback. Browser development keeps its current host.
const host = isTauri ? '127.0.0.1' : window.location.hostname || 'localhost';

export const API_BASE = `http://${host}:${port}/api`;
export const WS_BASE = `ws://${host}:${port}`;
export const NEOSWARM_DEFAULT_PROXY_URL = 'https://api.neoswarm.ai';