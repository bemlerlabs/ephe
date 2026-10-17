'use client'

import type { EngineState, HealthInfo } from '@/lib/api/types'

/** The engine state of a health document, from whichever field the backend filled. */
export function engineStateOf(info: HealthInfo): EngineState {
  return info.engine_state ?? (info.engine_online ? 'ok' : 'unreachable')
}

export function providerLabel(type: string | null | undefined, t: (key: string) => string): string {
  switch (type) {
    case 'local_ollama':
      return t('settings.providerLabelLocalOllama')
    case 'custom_ollama':
      return t('settings.providerLabelCustomOllama')
    case 'openai_compatible':
      return t('settings.providerLabelOpenAiCompat')
    default:
      return type ?? '—'
  }
}

// G5: only de/en — the only i18n resources that exist (fr/es would be fake).
export const languageOptions = [
  { code: 'de', label: 'Deutsch' },
  { code: 'en', label: 'English' },
]
