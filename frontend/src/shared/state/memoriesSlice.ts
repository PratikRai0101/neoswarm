import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const MEMORY_API = `${API_BASE}/memory`;

export type MemoryCategory = 'fact' | 'preference' | 'instruction' | 'note';

export interface Memory {
  id: string;
  content: string;
  category: MemoryCategory;
  tags: string[];
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
}

export interface CreateMemoryInput {
  content: string;
  category: MemoryCategory;
  tags: string[];
}

export interface UpdateMemoryInput {
  id: string;
  content?: string;
  category?: MemoryCategory;
  tags?: string[];
}

interface MemoriesState {
  items: Record<string, Memory>;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

const initialState: MemoriesState = {
  items: {},
  loading: false,
  saving: false,
  error: null,
};

async function memoryRequest(path = '', init?: RequestInit): Promise<Memory> {
  const response = await fetch(`${MEMORY_API}${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Memory request failed (${response.status})`);
  if (!data.memory?.id) throw new Error('Backend returned an invalid memory');
  return data.memory as Memory;
}

export const fetchMemories = createAsyncThunk('memories/fetchAll', async (query: string) => {
  const response = await fetch(`${MEMORY_API}?q=${encodeURIComponent(query)}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Failed to load memories');
  return (data.memories || []) as Memory[];
});

export const createMemory = createAsyncThunk(
  'memories/create',
  async (input: CreateMemoryInput) => memoryRequest('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }),
);

export const updateMemory = createAsyncThunk(
  'memories/update',
  async ({ id, ...patch }: UpdateMemoryInput) => memoryRequest(`/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }),
);

export const deleteMemory = createAsyncThunk('memories/delete', async (id: string) => {
  const response = await fetch(`${MEMORY_API}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Failed to delete memory');
  return id;
});

const memoriesSlice = createSlice({
  name: 'memories',
  initialState,
  reducers: {
    clearMemoryError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchMemories.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMemories.fulfilled, (state, action) => {
        state.loading = false;
        state.items = Object.fromEntries(action.payload.map((memory) => [memory.id, memory]));
      })
      .addCase(fetchMemories.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to load memories';
      });

    for (const thunk of [createMemory, updateMemory]) {
      builder
        .addCase(thunk.pending, (state) => {
          state.saving = true;
          state.error = null;
        })
        .addCase(thunk.fulfilled, (state, action) => {
          state.saving = false;
          state.items[action.payload.id] = action.payload;
        })
        .addCase(thunk.rejected, (state, action) => {
          state.saving = false;
          state.error = action.error.message || 'Memory request failed';
        });
    }

    builder
      .addCase(deleteMemory.fulfilled, (state, action) => {
        delete state.items[action.payload];
      })
      .addCase(deleteMemory.rejected, (state, action) => {
        state.error = action.error.message || 'Failed to delete memory';
      });
  },
});

export const { clearMemoryError } = memoriesSlice.actions;
export default memoriesSlice.reducer;
