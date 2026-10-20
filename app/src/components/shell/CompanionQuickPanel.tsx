'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getSettings, saveSections } from '@/lib/api'
import { seedDeepSettings, useDeepBool } from '@/lib/deepSettings'
import type { RunState } from '@/components/shell/AgenticBar'
import {
  CompanionActor,
  type CompanionHandle,
  type CompanionSpecies,
} from '@/components/shell/CompanionActor'
import { companionMood } from '@/components/shell/companionState'

/**
 * The actor's quick panel: the current run word and three or four controls.
 * Rest is a session state (not a register write); sound writes the existing
 * `appearance.companion_sound` through the register's own endpoint.
 */
export function CompanionQuickPanel({
  runState,
  species,
  scale,
  still,
  placement,
}: {
  runState: RunState
  species: CompanionSpecies
  scale: number
  still: boolean
  placement: 'composer' | 'header'
}) {
  const { t } = useTranslation()
  const soundValue = useDeepBool('appearance.companion_sound', true)
  const [open, setOpen] = useState(false)
  const [resting, setResting] = useState(false)
  const [sound, setSound] = useState(soundValue)
  const [error, setError] = useState('')
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const actor = useRef<CompanionHandle>(null)
  const wasOpen = useRef(false)

  useEffect(() => {
    setSound(soundValue)
  }, [soundValue])

  useEffect(() => {
    if (open) {
      panel.current
        ?.querySelector<HTMLButtonElement>('[data-testid="companion-popover-settings"]')
        ?.focus()
    } else if (wasOpen.current) {
      trigger.current?.focus()
    }
    wasOpen.current = open
  }, [open])

  const close = useCallback(() => setOpen(false), [])

  const toggle = () => {
    if (!open) {
      actor.current?.turnTo(14)
      actor.current?.burst()
    }
    setOpen((value) => !value)
  }

  const onPanelKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close()
      return
    }
    if (event.key !== 'Tab' || !panel.current) return
    const buttons = [...panel.current.querySelectorAll<HTMLButtonElement>('button:not([disabled])')]
    if (buttons.length === 0) return
    const first = buttons[0]
    const last = buttons[buttons.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  async function toggleSound() {
    const next = !sound
    setSound(next)
    setError('')
    try {
      const settings = await getSettings()
      const appearance = (settings.deep ?? []).find((section) => section.key === 'appearance')
      if (!appearance) throw new Error('appearance register missing')
      const values: Record<string, string | number | boolean> = {}
      for (const field of appearance.fields) {
        values[field.key] = field.value ?? field.default ?? ''
      }
      values['appearance.companion_sound'] = next
      await saveSections({ appearance: values })
      seedDeepSettings(
        (settings.deep ?? []).map((section) =>
          section.key === 'appearance'
            ? {
                ...section,
                fields: section.fields.map((field) =>
                  field.key === 'appearance.companion_sound' ? { ...field, value: next } : field,
                ),
              }
            : section,
        ),
      )
    } catch (cause) {
      setSound(!next)
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  function openSettings() {
    close()
    window.dispatchEvent(new CustomEvent('ephe:open-settings'))
    window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'appearance' } }))
  }

  const mood = resting ? 'rest' : companionMood(runState)

  return (
    <>
      <button
        ref={trigger}
        type="button"
        data-testid="companion-trigger"
        aria-label={t('settings.companionQuickLabel')}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={toggle}
        className="companion-trigger focus-ring"
      >
        <CompanionActor
          ref={actor}
          species={species}
          scale={scale}
          still={still || resting}
          flying={mood === 'moving'}
          size={placement === 'header' ? 'header' : 'workspace'}
        />
      </button>
      {open && (
        <div
          ref={panel}
          role="dialog"
          aria-label={t('settings.companionQuickLabel')}
          data-testid="companion-popover"
          className={`companion-popover float-surface${placement === 'header' ? ' is-header' : ''}`}
          onKeyDown={onPanelKeyDown}
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p data-testid="companion-state-word" className="text-scale-ui font-medium text-ink">
                {t(`workbench.${runState}`)}
              </p>
              <p className="pt-0.5 text-scale-data text-ink-faint">
                {t('settings.companionQuickHint')}
              </p>
            </div>
            <button
              type="button"
              data-testid="companion-popover-close"
              aria-label={t('settings.companionClose')}
              onClick={close}
              className="focus-ring rounded-lg px-2 py-1 text-scale-data text-ink-faint hover:bg-surface-interactive hover:text-ink"
            >
              ×
            </button>
          </div>
          <div className="mt-2 flex flex-col gap-0.5">
            <button
              type="button"
              data-testid="companion-popover-settings"
              onClick={openSettings}
              className="focus-ring rounded-lg px-2.5 py-2 text-left text-scale-ui text-ink-soft hover:bg-surface-interactive hover:text-ink"
            >
              {t('settings.companionSettings')}
            </button>
            <button
              type="button"
              data-testid="companion-popover-rest"
              aria-pressed={resting}
              onClick={() => setResting((value) => !value)}
              className="focus-ring rounded-lg px-2.5 py-2 text-left text-scale-ui text-ink-soft hover:bg-surface-interactive hover:text-ink"
            >
              {resting ? t('settings.companionWake') : t('settings.companionRest')}
            </button>
            <button
              type="button"
              data-testid="companion-popover-sound"
              aria-pressed={sound}
              onClick={() => void toggleSound()}
              className="focus-ring rounded-lg px-2.5 py-2 text-left text-scale-ui text-ink-soft hover:bg-surface-interactive hover:text-ink"
            >
              {t('settings.companionSound')}:{' '}
              {sound ? t('settings.companionSoundOn') : t('settings.companionSoundOff')}
            </button>
          </div>
          {error && (
            <p
              role="alert"
              data-testid="companion-popover-error"
              className="px-2.5 pt-1 text-scale-data text-status-danger"
            >
              {t('settings.companionSaveFailed')}: {error}
            </p>
          )}
        </div>
      )}
    </>
  )
}
