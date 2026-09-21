import { useEffect, useState } from 'react';
import { dashboardWs } from './ws/WebSocketManager';
import { API_BASE } from './config';

// ---------------------------------------------------------------------------
// App tool-grant requests (deny-by-default gate for vibe-coded apps).
//
// The backend broadcasts apps:tool_grant_request when an app calls an
// ungranted tool. This module keeps the pending set, syncs it over the
// dashboard socket, and resolves decisions through POST /api/apps/tools/grant.
// Silence/timeout reads as deny server-side; dismissing here just hides the
// card (the call already failed or will time out).
// ---------------------------------------------------------------------------

export interface AppGrantRequest {
  request_id: string;
  app_id: string;
  app_name: string;
  tool_key: string;
  tool_label: string;
  args_preview: string;
}

const pending = new Map<string, AppGrantRequest>();

type GrantListener = (requests: AppGrantRequest[]) => void;
const listeners = new Set<GrantListener>();

function snapshot(): AppGrantRequest[] {
  return Array.from(pending.values());
}

function notify() {
  const list = snapshot();
  listeners.forEach((fn) => fn(list));
}

export function addAppGrantRequest(req: AppGrantRequest): void {
  if (!req?.request_id || pending.has(req.request_id)) return;
  pending.set(req.request_id, req);
  notify();
}

export function removeAppGrantRequest(requestId: string): void {
  if (pending.delete(requestId)) notify();
}

export function subscribeAppGrants(fn: GrantListener): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export async function resolveAppGrant(
  requestId: string,
  allow: boolean,
  remember: boolean,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/apps/tools/grant`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: requestId, allow, remember }),
    });
    const data = await res.json().catch(() => ({}));
    removeAppGrantRequest(requestId);
    return data?.ok === true;
  } catch {
    return false;
  }
}

export function useAppGrantRequests(): AppGrantRequest[] {
  const [requests, setRequests] = useState<AppGrantRequest[]>(() => snapshot());

  useEffect(() => {
    setRequests(snapshot());
    const unsubStore = subscribeAppGrants(setRequests);
    const unsubWs = dashboardWs.on('apps:tool_grant_request', (data: Record<string, any>) => {
      addAppGrantRequest({
        request_id: String(data.request_id ?? ''),
        app_id: String(data.app_id ?? ''),
        app_name: String(data.app_name ?? data.app_id ?? 'An app'),
        tool_key: String(data.tool_key ?? ''),
        tool_label: String(data.tool_label ?? data.tool_key ?? 'a tool'),
        args_preview: String(data.args_preview ?? ''),
      });
    });
    return () => {
      unsubStore();
      unsubWs();
    };
  }, []);

  return requests;
}
