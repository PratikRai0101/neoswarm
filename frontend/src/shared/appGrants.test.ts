import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const dashboardWs = { on: vi.fn(), send: vi.fn() };
  return { dashboardWs };
});

vi.mock('./ws/WebSocketManager', () => ({ dashboardWs: mocks.dashboardWs }));
vi.mock('./config', () => ({ API_BASE: 'http://127.0.0.1:8324/api' }));

import {
  addAppGrantRequest,
  removeAppGrantRequest,
  resolveAppGrant,
  subscribeAppGrants,
} from './appGrants';

const REQ = {
  request_id: 'req-1',
  app_id: 'app-1',
  app_name: 'Demo App',
  tool_key: 'tool-id:X',
  tool_label: 'X',
  args_preview: '{"a": 1}',
};

describe('app grant store', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    removeAppGrantRequest('req-1');
    removeAppGrantRequest('req-2');
  });

  it('adds, dedupes, and removes requests with notifications', () => {
    const seen: string[][] = [];
    const unsub = subscribeAppGrants((list) => seen.push(list.map((r) => r.request_id)));
    addAppGrantRequest({ ...REQ });
    addAppGrantRequest({ ...REQ });
    expect(seen).toEqual([['req-1']]);
    removeAppGrantRequest('req-1');
    expect(seen).toEqual([['req-1'], []]);
    unsub();
  });

  it('resolve posts the decision and clears the card', async () => {
    (globalThis.fetch as unknown) = vi.fn(async () => ({
      ok: true,
      json: async () => ({ ok: true }),
    }));
    addAppGrantRequest({ ...REQ });
    const ok = await resolveAppGrant('req-1', true, true);
    expect(ok).toBe(true);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/apps/tools/grant'),
      expect.objectContaining({ method: 'POST' }),
    );
    const body = JSON.parse((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ request_id: 'req-1', allow: true, remember: true });
  });

  it('resolve returns false when the network fails', async () => {
    (globalThis.fetch as unknown) = vi.fn(async () => {
      throw new Error('down');
    });
    expect(await resolveAppGrant('req-1', false, false)).toBe(false);
  });
});
