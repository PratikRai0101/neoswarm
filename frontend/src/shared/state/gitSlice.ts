import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const GIT_API = `${API_BASE}/git`;

export interface GitStatusEntry {
  index: string;
  worktree: string;
  path: string;
  original_path: string | null;
}

export interface GitStatus {
  path: string;
  root: string;
  branch: string;
  upstream: string | null;
  ahead: number;
  behind: number;
  clean: boolean;
  entries: GitStatusEntry[];
}

export interface GitDiff {
  path: string;
  staged: boolean;
  diff: string;
  truncated: boolean;
}

export interface GitBranch {
  name: string;
  current: boolean;
  upstream: string | null;
}

interface GitState {
  status: GitStatus | null;
  diff: GitDiff | null;
  branches: GitBranch[];
  loading: boolean;
  committing: boolean;
  error: string | null;
}

const initialState: GitState = {
  status: null,
  diff: null,
  branches: [],
  loading: false,
  committing: false,
  error: null,
};

async function parseResponse(response: Response): Promise<any> {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Git request failed (${response.status})`);
  return data;
}

export const fetchGitStatus = createAsyncThunk('git/status', async (path: string) => {
  const data = await parseResponse(await fetch(`${GIT_API}/status?path=${encodeURIComponent(path)}`));
  return data.status as GitStatus;
});

export const fetchGitDiff = createAsyncThunk('git/diff', async ({ path, staged = false }: { path: string; staged?: boolean }) => {
  const data = await parseResponse(await fetch(`${GIT_API}/diff?path=${encodeURIComponent(path)}&staged=${staged}`));
  return data.diff as GitDiff;
});

export const fetchGitBranches = createAsyncThunk('git/branches', async (path: string) => {
  const data = await parseResponse(await fetch(`${GIT_API}/branches?path=${encodeURIComponent(path)}`));
  return data.branches as GitBranch[];
});

export const createGitCommit = createAsyncThunk('git/commit', async ({ path, message, stageAll }: { path: string; message: string; stageAll: boolean }) => {
  const response = await fetch(`${GIT_API}/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, message, stage_all: stageAll }),
  });
  const data = await parseResponse(response);
  return data.commit as { path: string; commit: string; message: string };
});

const gitSlice = createSlice({
  name: 'git',
  initialState,
  reducers: {
    clearGitError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchGitStatus.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchGitStatus.fulfilled, (state, action) => { state.loading = false; state.status = action.payload; })
      .addCase(fetchGitStatus.rejected, (state, action) => { state.loading = false; state.error = action.error.message || 'Failed to load Git status'; })
      .addCase(fetchGitDiff.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchGitDiff.fulfilled, (state, action) => { state.loading = false; state.diff = action.payload; })
      .addCase(fetchGitDiff.rejected, (state, action) => { state.loading = false; state.error = action.error.message || 'Failed to load Git diff'; })
      .addCase(fetchGitBranches.fulfilled, (state, action) => { state.branches = action.payload; })
      .addCase(fetchGitBranches.rejected, (state, action) => { state.error = action.error.message || 'Failed to load Git branches'; })
      .addCase(createGitCommit.pending, (state) => { state.committing = true; state.error = null; })
      .addCase(createGitCommit.fulfilled, (state) => { state.committing = false; state.diff = null; })
      .addCase(createGitCommit.rejected, (state, action) => { state.committing = false; state.error = action.error.message || 'Failed to create Git commit'; });
  },
});

export const { clearGitError } = gitSlice.actions;
export default gitSlice.reducer;
