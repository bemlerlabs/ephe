import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getModelProviders, setModelProvider } from '@/lib/api'
import { scanEnvironment } from '@/lib/api/environment'
import { isJunkModel } from '@/lib/modelFilter'
import { gateSnapshot, loadSetupGate } from '@/lib/setupGate'
import { toastBus } from '@/lib/toast'
import { useChatStore } from '@/store/chatStore'
import type { ModelChipEntry } from './composerModelEntries'
import { buildScanEntries, mergeScanEntries } from './composerModelEntries'
import { anchorAbove, type MenuPos } from './composerPopups'

/**
 * K3 Z24 / P3 wave 2026-10-05: model & provider selection for the composer —
 * chip state, provider list (incl. the environment-scan merge), setup-state
 * re-entry and the live-provider switch. Extracted from ChatInput.tsx.
 */
export function useComposerModelSelection() {
  const { t } = useTranslation()
  // Never show a model that was never chosen: seeded from the last real backend
  // state (localStorage), otherwise empty until /api/model/providers answers.
  // The strong default 'gemma4:e4b' flickered up as a chip after an engine
  // reload and suggested a silent model fallback (finding 2026-10-01).
  const [model, setModel] = useState(() => {
    try {
      return localStorage.getItem('ephe.lastModel') || ''
    } catch {
      return ''
    }
  })
  // Badge: the real offline status of the active provider (no hardcoded "local" value)
  const [offlineCapable, setOfflineCapable] = useState(true)
  // K3 Z24 (reference parity): the model chip is the only engine entry point in
  // the composer — clicking opens the provider picker, choosing switches live.
  const [providers, setProviders] = useState<ModelChipEntry[]>([])
  const [activeP, setActiveP] = useState('')
  // W19: setup re-entry — with no engine chosen (skip/setup mode) the engine chip
  // shows the way to the setup page instead of the silent default.
  const [needsSetup, setNeedsSetup] = useState(false)
  const [chipOpen, setChipOpen] = useState(false)
  const modelChipRef = useRef<HTMLButtonElement | null>(null)
  const [modelMenuPos, setModelMenuPos] = useState<MenuPos | null>(null)

  // Load the active model + offline status from settings (instead of hardcoded)
  useEffect(() => {
    let cancelled = false
    getModelProviders()
      .then((r) => {
        if (cancelled) return
        if (r.active?.model) {
          setModel(r.active.model)
          try {
            localStorage.setItem('ephe.lastModel', r.active.model)
          } catch {
            /* Private Mode: the chip falls back to the loading state */
          }
        }
        setOfflineCapable(Boolean(r.active?.offline_capable))
        // The active descriptor carries the provider id as 'provider' (backend shape).
        const act = r.active as unknown as { provider?: string; type?: string }
        setActiveP(act?.provider ?? act?.type ?? '')
        // Wave 3 (cost monitor): the price table goes into the store once — the
        // status bar computes the USD chip from it (null = no price → no chip).
        // Optional chaining: test store mocks do not know getState — the .then
        // chain must not die on that (otherwise providers stays empty).
        useChatStore.getState?.().setEnginePricing?.(r.pricing ?? null)
        const list = (r.providers ?? []) as ModelChipEntry[]
        // F-J (t5 audit): keep "test"/embedding models out of the history.
        const clean = list.filter((p) => !isJunkModel(p.model ?? p.id))
        setProviders(clean)
        // B8 (generic): the environment scan is ALWAYS merged — presets first,
        // deduplicated across them (provider id, model); that is how the models of
        // the tools found on this machine become selectable even when the provider
        // table is already filled.
        scanEnvironment()
          .then((env) => {
            if (cancelled) return
            const merged = mergeScanEntries(clean, buildScanEntries(env?.tools ?? []))
            setProviders(merged)
          })
          .catch(() => {})
      })
      .catch(() => {}) // Backend offline → keep the default badge
    return () => {
      cancelled = true
    }
  }, [])

  // W19: setup re-entry — with no engine chosen (skip/setup mode) the engine chip
  // shows the way to the setup page instead of the silent default.
  //
  // R25 (perceived latency): this used to send its own `GET /api/setup/status`, a second
  // copy of the call the gate had just made — measured 320 ms each on the real engine, so
  // opening the chat paid the same upstream round trip twice. It reads the gate's answer
  // instead: same fact, one request per app load.
  useEffect(() => {
    let cancelled = false
    void loadSetupGate().then(() => {
      if (!cancelled) setNeedsSetup(!gateSnapshot().configured)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const syncModelMenuPos = useCallback(() => {
    const el = modelChipRef.current
    if (!el) return
    setModelMenuPos(anchorAbove(el.getBoundingClientRect()))
  }, [])

  const pickProvider = (id: string, model?: string, baseUrl?: string) => {
    setChipOpen(false)
    void setModelProvider(id, model, baseUrl)
      .then((r) => {
        // F-7: the chip flips to the new provider only after the backend
        // confirms — never before (no lying accent state).
        setActiveP(id)
        if (r.active?.model) {
          setModel(r.active.model)
          try {
            localStorage.setItem('ephe.lastModel', r.active.model)
          } catch {
            /* Private Mode */
          }
        }
        // P1b: model/provider switch — the context window may have changed;
        // ChatLayout reloads it through this event (re-fetch).
        window.dispatchEvent(new CustomEvent('ephe:model-changed'))
      })
      .catch(() => toastBus.error(t('common.changeFailed')))
  }

  // P1-10: the badge text follows the active provider (Ollama local/remote, or an
  // OpenAI-compatible engine); without a backend answer the offline default applies.
  const engineLabel =
    activeP === 'openai_compatible'
      ? t('chat.badgeRemoteEngine')
      : activeP === 'custom_ollama'
        ? t('chat.badgeRemoteOllama')
        : activeP === 'local_ollama'
          ? t('chat.badgeLocalOllama')
          : offlineCapable
            ? t('chat.offlineCapableLocal')
            : t('chat.offlineCapableRemote')

  return {
    model,
    offlineCapable,
    providers,
    activeP,
    needsSetup,
    chipOpen,
    setChipOpen,
    modelChipRef,
    modelMenuPos,
    syncModelMenuPos,
    pickProvider,
    engineLabel,
  }
}
