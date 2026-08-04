import { configureStore } from '@reduxjs/toolkit';
import tempStateReducer from './tempStateSlice';
import agentsReducer from './agentsSlice';
import skillsReducer from './skillsSlice';
import toolsReducer from './toolsSlice';
import modesReducer from './modesSlice';
import settingsReducer from './settingsSlice';
import mcpRegistryReducer from './mcpRegistrySlice';
import skillRegistryReducer from './skillRegistrySlice';
import outputsReducer from './outputsSlice';
import dashboardLayoutReducer from './dashboardLayoutSlice';
import dashboardsReducer from './dashboardsSlice';
import updateReducer from './updateSlice';
import analyticsReducer from './analyticsSlice';
import modelsReducer from './modelsSlice';
import missionsReducer from './missionsSlice';
import schedulesReducer from './schedulesSlice';
import memoriesReducer from './memoriesSlice';
import gitReducer from './gitSlice';
import artifactsReducer from './artifactsSlice';
import terminalsReducer from './terminalsSlice';
import sshReducer from './sshSlice';
import imagesReducer from './imagesSlice';

export const store = configureStore({
  reducer: {
    tempState: tempStateReducer,
    agents: agentsReducer,
    skills: skillsReducer,
    tools: toolsReducer,
    modes: modesReducer,
    settings: settingsReducer,
    mcpRegistry: mcpRegistryReducer,
    skillRegistry: skillRegistryReducer,
    outputs: outputsReducer,
    dashboardLayout: dashboardLayoutReducer,
    dashboards: dashboardsReducer,
    update: updateReducer,
    analytics: analyticsReducer,
    models: modelsReducer,
    missions: missionsReducer,
    schedules: schedulesReducer,
    memories: memoriesReducer,
    git: gitReducer,
    artifacts: artifactsReducer,
    terminals: terminalsReducer,
    ssh: sshReducer,
    images: imagesReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
