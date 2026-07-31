import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const MISSIONS_API = `${API_BASE}/agents/missions`;

export type MissionStatus =
  | 'pending'
  | 'decomposing'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type MissionTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface MissionTask {
  id: string;
  description: string;
  status: MissionTaskStatus;
  assigned_worker_id: string | null;
  result: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface MissionWorker {
  id: string;
  name: string;
  status: 'idle' | 'busy' | 'completed' | 'error';
  current_task_id: string | null;
  session_id: string | null;
  model: string;
}

export interface Mission {
  id: string;
  mission: string;
  model: string;
  provider: string | null;
  execution_mode: 'parallel' | 'sequential';
  target_directory: string | null;
  isolate_workers: boolean;
  status: MissionStatus;
  created_at: string;
  completed_at: string | null;
  final_result: string | null;
  error: string | null;
  tasks: MissionTask[];
  workers: MissionWorker[];
}

export interface CreateMissionInput {
  mission: string;
  workers: number;
  model: string;
  provider: string;
  execution_mode: 'parallel' | 'sequential';
  target_directory?: string | null;
  isolate_workers?: boolean;
}

interface MissionsState {
  items: Record<string, Mission>;
  loading: boolean;
  creating: boolean;
  error: string | null;
}

const initialState: MissionsState = {
  items: {},
  loading: false,
  creating: false,
  error: null,
};

async function missionRequest(path = '', init?: RequestInit): Promise<Mission> {
  const response = await fetch(`${MISSIONS_API}${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Mission request failed (${response.status})`);
  }
  if (!data.mission?.id) throw new Error('Backend returned an invalid mission');
  return data.mission as Mission;
}

export const fetchMissions = createAsyncThunk('missions/fetchAll', async () => {
  const response = await fetch(MISSIONS_API);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Failed to load missions');
  return (data.missions || []) as Mission[];
});

export const fetchMission = createAsyncThunk('missions/fetchOne', async (missionId: string) =>
  missionRequest(`/${encodeURIComponent(missionId)}`),
);

export const createMission = createAsyncThunk(
  'missions/create',
  async (input: CreateMissionInput) =>
    missionRequest('', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),
);

export const startMission = createAsyncThunk('missions/start', async (missionId: string) =>
  missionRequest(`/${encodeURIComponent(missionId)}/start`, { method: 'POST' }),
);

export const cancelMission = createAsyncThunk('missions/cancel', async (missionId: string) =>
  missionRequest(`/${encodeURIComponent(missionId)}/cancel`, { method: 'POST' }),
);

const missionsSlice = createSlice({
  name: 'missions',
  initialState,
  reducers: {
    clearMissionError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchMissions.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMissions.fulfilled, (state, action) => {
        state.loading = false;
        state.items = Object.fromEntries(action.payload.map((mission) => [mission.id, mission]));
      })
      .addCase(fetchMissions.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to load missions';
      })
      .addCase(createMission.pending, (state) => {
        state.creating = true;
        state.error = null;
      })
      .addCase(createMission.fulfilled, (state, action) => {
        state.creating = false;
        state.items[action.payload.id] = action.payload;
      })
      .addCase(createMission.rejected, (state, action) => {
        state.creating = false;
        state.error = action.error.message || 'Failed to create mission';
      });

    for (const thunk of [fetchMission, startMission, cancelMission]) {
      builder.addCase(thunk.fulfilled, (state, action) => {
        state.items[action.payload.id] = action.payload;
        state.error = null;
      });
      builder.addCase(thunk.rejected, (state, action) => {
        state.error = action.error.message || 'Mission request failed';
      });
    }
  },
});

export const { clearMissionError } = missionsSlice.actions;
export default missionsSlice.reducer;
