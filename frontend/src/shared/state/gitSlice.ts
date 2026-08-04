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

export interface GitRemote {
  name: string;
  url: string;
}

export interface GitPushResult {
  path: string;
  remote: string;
  branch: string;
  set_upstream: boolean;
  output: string;
}

export interface GitPullRequest {
  path: string;
  url: string;
  title: string;
  base: string;
  head: string;
  draft: boolean;
}

interface GitState {
  status: GitStatus | null;
  diff: GitDiff | null;
  branches: GitBranch[];
  remotes: GitRemote[];
  lastPush: GitPushResult | null;
  lastPullRequest: GitPullRequest | null;
  loading: boolean;
  committing: boolean;
  pushing: boolean;
  creatingPullRequest: boolean;
  error: string | null;
}

const initialState: GitState = {
  status: null,
  diff: null,
  branches: [],
  remotes: [],
  lastPush: null,
  lastPullRequest: null,
  loading: false,
  committing: false,
  pushing: false,
  creatingPullRequest: false,
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

export const fetchGitRemotes = createAsyncThunk('git/remotes', async (path: string) => {
  const data = await parseResponse(await fetch(`${GIT_API}/remotes?path=${encodeURIComponent(path)}`));
  return data.remotes as GitRemote[];
});

export const pushGitBranch = createAsyncThunk('git/push', async ({ path, remote, branch, setUpstream = true }: { path: string; remote: string; branch?: string; setUpstream?: boolean }) => {
  const response = await fetch(`${GIT_API}/push`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, remote, branch, set_upstream: setUpstream }),
  });
  const data = await parseResponse(response);
  return data.push as GitPushResult;
});

export const createGitPullRequest = createAsyncThunk('git/pullRequest', async ({ path, title, body, base, head, remote, draft }: { path: string; title: string; body: string; base: string; head?: string; remote: string; draft: boolean }) => {
  const response = await fetch(`${GIT_API}/pull-request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, title, body, base, head, remote, draft }),
  });
  const data = await parseResponse(response);
  return data.pull_request as GitPullRequest;
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
      .addCase(fetchGitRemotes.fulfilled, (state, action) => { state.remotes = action.payload; })
      .addCase(fetchGitRemotes.rejected, (state, action) => { state.error = action.error.message || 'Failed to load Git remotes'; })
      .addCase(pushGitBranch.pending, (state) => { state.pushing = true; state.error = null; })
      .addCase(pushGitBranch.fulfilled, (state, action) => { state.pushing = false; state.lastPush = action.payload; })
      .addCase(pushGitBranch.rejected, (state, action) => { state.pushing = false; state.error = action.error.message || 'Failed to push Git branch'; })
      .addCase(createGitPullRequest.pending, (state) => { state.creatingPullRequest = true; state.error = null; })
      .addCase(createGitPullRequest.fulfilled, (state, action) => { state.creatingPullRequest = false; state.lastPullRequest = action.payload; })
      .addCase(createGitPullRequest.rejected, (state, action) => { state.creatingPullRequest = false; state.error = action.error.message || 'Failed to create pull request'; })
      .addCase(createGitCommit.pending, (state) => { state.committing = true; state.error = null; })
      .addCase(createGitCommit.fulfilled, (state) => { state.committing = false; state.diff = null; })
      .addCase(createGitCommit.rejected, (state, action) => { state.committing = false; state.error = action.error.message || 'Failed to create Git commit'; });
  },
});

export const { clearGitError } = gitSlice.actions;
export default gitSlice.reducer;
