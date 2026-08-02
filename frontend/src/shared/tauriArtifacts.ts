import { invoke } from '@tauri-apps/api/core';

export function isTauriRuntime(): boolean {
  return Boolean((window as any).__TAURI_INTERNALS__);
}

export async function openArtifactInDefaultApp(artifactId: string, previewUrl: string): Promise<void> {
  if (!isTauriRuntime()) {
    window.open(previewUrl, '_blank', 'noopener,noreferrer');
    return;
  }
  await invoke('open_artifact', { artifactId });
}
