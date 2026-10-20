// I3-4: the client line to the deep settings.
//
// The server holds the register (core/settings_schema.py) and the descriptions
// (core/settings_hints.py); GET /api/settings brings both. Until now the PWA
// only read the sections inside the settings panel — no value was applied. This
// file is the only place where a client consumer reads a field, and
// it applies the appearance values to the <html> element so that a slider in
// the panel changes the app right away.
//
// A missing register (backend unreachable, an older response without 'deep')
// is not an error case: the accessors return the fallback they were handed and
// the app keeps running on its own defaults.

import { useSyncExternalStore } from 'react'
import { getSettings } from '@/lib/api'
import type { DeepSection } from '@/types'

/** Base of --ui-font-size in globals.css; 100 % font size = this value. */
export const UI_FONT_SIZE_BASE_PX = 15

const values = new Map<string, string | number | boolean | null>()
const listeners = new Set<() => void>()

function notify(): void {
  for (const listener of [...listeners]) listener()
}

export function subscribeDeepSettings(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function raw(key: string): string | number | boolean | null | undefined {
  return values.get(key)
}

export function deepValue(key: string, fallback: string | number | boolean | null = null) {
  const value = raw(key)
  return value === undefined ? fallback : value
}

export function deepBool(key: string, fallback = false): boolean {
  const value = raw(key)
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const low = value.trim().toLowerCase()
    if (['true', '1', 'yes', 'on', 'ja'].includes(low)) return true
    if (['false', '0', 'no', 'off', 'nein', ''].includes(low)) return false
  }
  return fallback
}

export function deepNumber(key: string, fallback = 0): number {
  const value = raw(key)
  const num = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(num) ? num : fallback
}

export function deepSelect(key: string, fallback = ''): string {
  const value = raw(key)
  return typeof value === 'string' && value !== '' ? value : fallback
}

export function deepText(key: string, fallback = ''): string {
  const value = raw(key)
  return typeof value === 'string' ? value : fallback
}

/**
 * Put the appearance on the <html> element. Deliberately idempotent: the same
 * call after every seed, so a save in the panel takes effect without a reload.
 *  - font_scale: 80-150 % on --ui-font-size, the app's only type-size step.
 *  - animations_enabled: html.no-motion, the same hard switch-off that
 *    prefers-reduced-motion brings — here chosen by the user.
 */
/** The chat reading step: the interface scale times the conversation's own factor. */
export function chatFontSizePx(): number {
  const ui = Math.min(150, Math.max(80, deepNumber('appearance.font_scale', 100)))
  const chat = Math.min(150, Math.max(80, deepNumber('appearance.chat_font_scale', 100)))
  return Math.round((UI_FONT_SIZE_BASE_PX - 2) * (ui / 100) * (chat / 100) * 100) / 100
}

/** The transcript's maximum reading width in pixels. */
export function chatReadingWidthPx(): number {
  return Math.round(Math.min(1200, Math.max(480, deepNumber('appearance.reading_width', 768))))
}

export function applyDeepAppearance(): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const scale = Math.min(150, Math.max(80, deepNumber('appearance.font_scale', 100)))
  root.style.setProperty(
    '--ui-font-size',
    `${Math.round(UI_FONT_SIZE_BASE_PX * (scale / 100) * 100) / 100}px`,
  )
  root.style.setProperty('--chat-font-size', `${chatFontSizePx()}px`)
  root.style.setProperty('--chat-reading-width', `${chatReadingWidthPx()}px`)
  const accent = deepSelect('appearance.accent', 'ember')
  root.dataset.accent = ['ember', 'indigo', 'plum', 'mono'].includes(accent) ? accent : 'ember'
  root.classList.toggle('no-motion', !deepBool('appearance.animations_enabled', true))
}

/** Put the register state into the store and re-apply the appearance. */
export function seedDeepSettings(sections: DeepSection[] | null): void {
  values.clear()
  for (const section of sections ?? []) {
    for (const field of section.fields) {
      values.set(field.key, field.value ?? field.default ?? null)
    }
  }
  applyDeepAppearance()
  notify()
}

/** On start: fetch the register and apply it. Without a backend all defaults stay. */
export async function initDeepSettings(): Promise<void> {
  try {
    const settings = await getSettings()
    seedDeepSettings(settings.deep ?? null)
  } catch {
    applyDeepAppearance()
  }
}

export function useDeepBool(key: string, fallback = false): boolean {
  return useSyncExternalStore(
    subscribeDeepSettings,
    () => deepBool(key, fallback),
    () => fallback,
  )
}

export function useDeepSelect(key: string, fallback = ''): string {
  return useSyncExternalStore(
    subscribeDeepSettings,
    () => deepSelect(key, fallback),
    () => fallback,
  )
}

export function useDeepNumber(key: string, fallback = 0): number {
  return useSyncExternalStore(
    subscribeDeepSettings,
    () => deepNumber(key, fallback),
    () => fallback,
  )
}

export function useChatReadingWidth(): number {
  return useSyncExternalStore(subscribeDeepSettings, chatReadingWidthPx, () => 768)
}
