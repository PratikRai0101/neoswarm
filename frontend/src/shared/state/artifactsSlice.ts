import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const ARTIFACTS_API = `${API_BASE}/artifacts`;

export interface Artifact {
  id: string;
  name: string;
  description: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  created_at: string;
  content_url: string;
  download_url: string;
}

interface ArtifactsState {
  items: Record<string, Artifact>;
  loading: boolean;
  loaded: boolean;
  error: string | null;
}

const initialState: ArtifactsState = {
  items: {},
  loading: false,
  loaded: false,
  error: null,
};

export const fetchArtifacts = createAsyncThunk('artifacts/fetch', async () => {
  const response = await fetch(`${ARTIFACTS_API}/list`);
  if (!response.ok) throw new Error(`Artifact list failed: ${response.status}`);
  const data = (await response.json()) as { artifacts: Artifact[] };
  return data.artifacts;
});

export const deleteArtifact = createAsyncThunk('artifacts/delete', async (id: string) => {
  const response = await fetch(`${ARTIFACTS_API}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(`Artifact delete failed: ${response.status}`);
  return id;
});

const artifactsSlice = createSlice({
  name: 'artifacts',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchArtifacts.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchArtifacts.fulfilled, (state, action) => {
        state.loading = false;
        state.loaded = true;
        state.items = {};
        for (const artifact of action.payload) state.items[artifact.id] = artifact;
      })
      .addCase(fetchArtifacts.rejected, (state, action) => {
        state.loading = false;
        state.loaded = true;
        state.error = action.error.message || 'Could not load artifacts.';
      })
      .addCase(deleteArtifact.fulfilled, (state, action) => {
        delete state.items[action.payload];
      })
      .addCase(deleteArtifact.rejected, (state, action) => {
        state.error = action.error.message || 'Could not delete artifact.';
      });
  },
});

export default artifactsSlice.reducer;
