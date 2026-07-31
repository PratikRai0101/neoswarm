import type { ModelOption } from './state/modelsSlice';

export interface ModelSelection extends ModelOption {
  group: string;
  provider: string;
}

const PROVIDER_IDS: Record<string, string> = {
  anthropic: 'anthropic',
  google: 'google',
  gemini: 'google',
  ollama: 'ollama',
  openai: 'openai',
  openrouter: 'openrouter',
};

/** Convert a display group into the provider identifier expected by the API. */
export function providerIdForGroup(group: string): string {
  return PROVIDER_IDS[group.toLowerCase()] ?? group;
}

/** Flatten the grouped API catalog without losing custom-provider identity. */
export function flattenModelCatalog(
  byProvider: Record<string, ModelOption[]>,
): ModelSelection[] {
  return Object.entries(byProvider).flatMap(([group, models]) =>
    models.map((model) => ({
      ...model,
      group,
      provider: providerIdForGroup(group),
    })),
  );
}

/** Pick a configured preference when executable, otherwise the first model. */
export function selectExecutableModel(
  catalog: ModelSelection[],
  preferredModel?: string | null,
): ModelSelection | undefined {
  return catalog.find((choice) => choice.value === preferredModel) ?? catalog[0];
}
