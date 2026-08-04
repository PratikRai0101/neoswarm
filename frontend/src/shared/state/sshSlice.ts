import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const SSH_API = `${API_BASE}/ssh/profiles`;

export interface SSHProfile {
  id: string;
  name: string;
  host: string;
  user: string;
  port: number;
  identity_file: string | null;
  target: string;
  created_at: string;
  updated_at: string;
}

interface SSHState {
  items: Record<string, SSHProfile>;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

const initialState: SSHState = {
  items: {},
  loading: false,
  saving: false,
  error: null,
};

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const data = (await response.json()) as { detail?: string };
    return new Error(data.detail || fallback);
  } catch {
    return new Error(fallback);
  }
}

export const fetchSSHProfiles = createAsyncThunk('ssh/fetchProfiles', async () => {
  const response = await fetch(SSH_API);
  if (!response.ok) throw await parseError(response, 'Could not load SSH profiles.');
  const data = (await response.json()) as { profiles: SSHProfile[] };
  return data.profiles;
});

export const createSSHProfile = createAsyncThunk(
  'ssh/createProfile',
  async (profile: { name: string; host: string; user: string; port: number; identity_file?: string }) => {
    const response = await fetch(SSH_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    if (!response.ok) throw await parseError(response, 'Could not save SSH profile.');
    return (await response.json()) as SSHProfile;
  },
);

export const deleteSSHProfile = createAsyncThunk('ssh/deleteProfile', async (id: string) => {
  const response = await fetch(`${SSH_API}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw await parseError(response, 'Could not delete SSH profile.');
  return id;
});

const sshSlice = createSlice({
  name: 'ssh',
  initialState,
  reducers: {
    clearSSHError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSSHProfiles.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSSHProfiles.fulfilled, (state, action) => {
        state.loading = false;
        state.items = {};
        for (const profile of action.payload) state.items[profile.id] = profile;
      })
      .addCase(fetchSSHProfiles.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Could not load SSH profiles.';
      })
      .addCase(createSSHProfile.pending, (state) => {
        state.saving = true;
        state.error = null;
      })
      .addCase(createSSHProfile.fulfilled, (state, action) => {
        state.saving = false;
        state.items[action.payload.id] = action.payload;
      })
      .addCase(createSSHProfile.rejected, (state, action) => {
        state.saving = false;
        state.error = action.error.message || 'Could not save SSH profile.';
      })
      .addCase(deleteSSHProfile.fulfilled, (state, action) => {
        delete state.items[action.payload];
      })
      .addCase(deleteSSHProfile.rejected, (state, action) => {
        state.error = action.error.message || 'Could not delete SSH profile.';
      });
  },
});

export const { clearSSHError } = sshSlice.actions;
export default sshSlice.reducer;
