import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const SCHEDULES_API = `${API_BASE}/schedules`;

export type ScheduleKind = 'interval' | 'once';
export type ScheduleStatus = 'scheduled' | 'running' | 'completed' | 'failed' | 'disabled';

export interface Schedule {
  id: string;
  name: string;
  prompt: string;
  kind: ScheduleKind;
  interval_seconds: number | null;
  run_at: string | null;
  model: string;
  provider: string | null;
  target_directory: string | null;
  enabled: boolean;
  status: ScheduleStatus;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
  last_session_id: string | null;
  last_error: string | null;
}

export interface CreateScheduleInput {
  name: string;
  prompt: string;
  kind: ScheduleKind;
  interval_seconds?: number;
  run_at?: string;
  model: string;
  provider?: string | null;
  target_directory?: string | null;
  enabled?: boolean;
}

export interface UpdateScheduleInput {
  id: string;
  name?: string;
  prompt?: string;
  kind?: ScheduleKind;
  interval_seconds?: number;
  run_at?: string;
  model?: string;
  provider?: string | null;
  target_directory?: string | null;
  enabled?: boolean;
}

interface SchedulesState {
  items: Record<string, Schedule>;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

const initialState: SchedulesState = {
  items: {},
  loading: false,
  saving: false,
  error: null,
};

async function scheduleRequest(path = '', init?: RequestInit): Promise<Schedule> {
  const response = await fetch(`${SCHEDULES_API}${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Schedule request failed (${response.status})`);
  if (!data.schedule?.id) throw new Error('Backend returned an invalid schedule');
  return data.schedule as Schedule;
}

export const fetchSchedules = createAsyncThunk('schedules/fetchAll', async () => {
  const response = await fetch(SCHEDULES_API);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Failed to load schedules');
  return (data.schedules || []) as Schedule[];
});

export const createSchedule = createAsyncThunk(
  'schedules/create',
  async (input: CreateScheduleInput) => scheduleRequest('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }),
);

export const updateSchedule = createAsyncThunk(
  'schedules/update',
  async ({ id, ...patch }: UpdateScheduleInput) => scheduleRequest(`/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }),
);

export const runSchedule = createAsyncThunk(
  'schedules/run',
  async (id: string) => scheduleRequest(`/${encodeURIComponent(id)}/run`, { method: 'POST' }),
);

export const deleteSchedule = createAsyncThunk('schedules/delete', async (id: string) => {
  const response = await fetch(`${SCHEDULES_API}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Failed to delete schedule');
  return id;
});

const schedulesSlice = createSlice({
  name: 'schedules',
  initialState,
  reducers: {
    clearScheduleError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSchedules.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSchedules.fulfilled, (state, action) => {
        state.loading = false;
        state.items = Object.fromEntries(action.payload.map((schedule) => [schedule.id, schedule]));
      })
      .addCase(fetchSchedules.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to load schedules';
      });

    for (const thunk of [createSchedule, updateSchedule, runSchedule]) {
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
          state.error = action.error.message || 'Schedule request failed';
        });
    }

    builder
      .addCase(deleteSchedule.fulfilled, (state, action) => {
        delete state.items[action.payload];
      })
      .addCase(deleteSchedule.rejected, (state, action) => {
        state.error = action.error.message || 'Failed to delete schedule';
      });
  },
});

export const { clearScheduleError } = schedulesSlice.actions;
export default schedulesSlice.reducer;
