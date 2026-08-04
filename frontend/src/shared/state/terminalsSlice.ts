import { createAsyncThunk, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const TERMINALS_API = `${API_BASE}/terminals`;

export type TerminalStatus = 'running' | 'stopped' | 'exited';

export interface Terminal {
  id: string;
  title: string;
  cwd: string;
  shell: string;
  connection: 'local' | 'ssh';
  target: string | null;
  ssh_profile_id: string | null;
  status: TerminalStatus;
  pid: number | null;
  exit_code: number | null;
  created_at: string;
  updated_at: string;
}

interface TerminalsState {
  items: Record<string, Terminal>;
  outputs: Record<string, string>;
  activeId: string | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

const initialState: TerminalsState = {
  items: {},
  outputs: {},
  activeId: null,
  loading: false,
  saving: false,
  error: null,
};

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const body = (await response.json()) as { detail?: string };
    return new Error(body.detail || fallback);
  } catch {
    return new Error(fallback);
  }
}

export const fetchTerminals = createAsyncThunk('terminals/fetch', async () => {
  const response = await fetch(`${TERMINALS_API}/list`);
  if (!response.ok) throw await parseError(response, 'Could not load terminals.');
  const data = (await response.json()) as { terminals: Terminal[] };
  return data.terminals;
});

export const createTerminal = createAsyncThunk(
  'terminals/create',
  async (request: { cwd?: string; shell?: string; title?: string; ssh_profile_id?: string }) => {
    const response = await fetch(`${TERMINALS_API}/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw await parseError(response, 'Could not create terminal.');
    return (await response.json()) as Terminal;
  },
);

export const startTerminal = createAsyncThunk('terminals/start', async (id: string) => {
  const response = await fetch(`${TERMINALS_API}/${id}/start`, { method: 'POST' });
  if (!response.ok) throw await parseError(response, 'Could not start terminal.');
  return (await response.json()) as Terminal;
});

export const deleteTerminal = createAsyncThunk('terminals/delete', async (id: string) => {
  const response = await fetch(`${TERMINALS_API}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw await parseError(response, 'Could not close terminal.');
  return id;
});

const terminalsSlice = createSlice({
  name: 'terminals',
  initialState,
  reducers: {
    setActiveTerminal(state, action: PayloadAction<string | null>) {
      state.activeId = action.payload;
    },
    updateTerminal(state, action: PayloadAction<Terminal>) {
      state.items[action.payload.id] = action.payload;
    },
    appendTerminalOutput(state, action: PayloadAction<{ id: string; output: string }>) {
      const current = state.outputs[action.payload.id] || '';
      state.outputs[action.payload.id] = (current + action.payload.output).slice(-200_000);
    },
    clearTerminalOutput(state, action: PayloadAction<string>) {
      state.outputs[action.payload] = '';
    },
    setTerminalError(state, action: PayloadAction<string>) {
      state.error = action.payload;
    },
    clearTerminalError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchTerminals.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchTerminals.fulfilled, (state, action) => {
        state.loading = false;
        state.items = {};
        for (const terminal of action.payload) state.items[terminal.id] = terminal;
        if (!state.activeId || !state.items[state.activeId]) {
          state.activeId = action.payload[0]?.id || null;
        }
      })
      .addCase(fetchTerminals.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Could not load terminals.';
      })
      .addCase(createTerminal.pending, (state) => {
        state.saving = true;
        state.error = null;
      })
      .addCase(createTerminal.fulfilled, (state, action) => {
        state.saving = false;
        state.items[action.payload.id] = action.payload;
        state.outputs[action.payload.id] = '';
        state.activeId = action.payload.id;
      })
      .addCase(createTerminal.rejected, (state, action) => {
        state.saving = false;
        state.error = action.error.message || 'Could not create terminal.';
      })
      .addCase(startTerminal.fulfilled, (state, action) => {
        state.items[action.payload.id] = action.payload;
        state.error = null;
      })
      .addCase(startTerminal.rejected, (state, action) => {
        state.error = action.error.message || 'Could not start terminal.';
      })
      .addCase(deleteTerminal.fulfilled, (state, action) => {
        const id = action.payload;
        delete state.items[id];
        delete state.outputs[id];
        if (state.activeId === id) {
          state.activeId = Object.keys(state.items)[0] || null;
        }
      })
      .addCase(deleteTerminal.rejected, (state, action) => {
        state.error = action.error.message || 'Could not close terminal.';
      });
  },
});

export const {
  setActiveTerminal,
  updateTerminal,
  appendTerminalOutput,
  clearTerminalOutput,
  setTerminalError,
  clearTerminalError,
} = terminalsSlice.actions;

export default terminalsSlice.reducer;
