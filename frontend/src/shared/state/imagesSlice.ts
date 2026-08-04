import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { API_BASE } from '@/shared/config';

const IMAGES_API = `${API_BASE}/images`;

export interface GeneratedArtifact {
  id: string;
  name: string;
  filename: string;
  media_type: string;
  size_bytes: number;
}

export interface GeneratedImage {
  artifact: GeneratedArtifact;
  revised_prompt: string | null;
}

interface ImagesState {
  generating: boolean;
  last: GeneratedImage | null;
  error: string | null;
}

const initialState: ImagesState = {
  generating: false,
  last: null,
  error: null,
};

async function parseError(response: Response): Promise<Error> {
  try {
    const data = (await response.json()) as { detail?: string };
    return new Error(data.detail || 'Image generation failed.');
  } catch {
    return new Error(`Image generation failed (${response.status}).`);
  }
}

export const generateImage = createAsyncThunk(
  'images/generate',
  async (request: { prompt: string; model: string; size: string; quality: string; output_format: string; background: string }) => {
    const response = await fetch(`${IMAGES_API}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw await parseError(response);
    return (await response.json()) as GeneratedImage;
  },
);

const imagesSlice = createSlice({
  name: 'images',
  initialState,
  reducers: {
    clearImageError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(generateImage.pending, (state) => {
        state.generating = true;
        state.error = null;
      })
      .addCase(generateImage.fulfilled, (state, action) => {
        state.generating = false;
        state.last = action.payload;
      })
      .addCase(generateImage.rejected, (state, action) => {
        state.generating = false;
        state.error = action.error.message || 'Image generation failed.';
      });
  },
});

export const { clearImageError } = imagesSlice.actions;
export default imagesSlice.reducer;
