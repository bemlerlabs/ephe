import { useState, useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Cpu,
  Server,
  PlugZap,
  Loader2,
  Check,
  AlertTriangle,
  KeyRound,
  ArrowRight,
  RefreshCw,
} from 'lucide-react'
import ErrorBoundary from '@/components/ui/ErrorBoundary'
import { storeEngineKey } from '@/lib/engineKey'
import ForestBackground from '@/components/dashboard/ForestBackground'
import EnvironmentTools from '@/components/shell/EnvironmentTools'
import { HeroMark } from '@/components/shell/HeroMark'
import { ModelPicker } from '@/components/model/ModelPicker'
import { rowsFromProbe } from '@/components/model/modelPickerTypes'
import {
  probeProvider,
  updateSettings,
  resetSetup,
  skipSetup,
  getSetupStatus,
  detectEngines,
  type DetectResponse,
  type EngineCandidate,
  type EngineState,
  type ProbeKeySource,
  type ProviderProbeResponse,
  type SetupRepair,
} from '@/lib/api'
import { forgetSetupGate } from '@/lib/setupGate'
import { announceSetupRepair } from '@/lib/companionRepair'
import { apiUrl } from '@/lib/api/http'
import { recommendOneClickSetup } from '@/lib/oneClickSetup'

type ProviderKind = 'local_ollama' | 'custom_ollama' | 'openai_compatible'

/** The engine label as the surface names it — the picker's group heading is the same. */
const ENGINE_LABEL_KEY: Record<ProviderKind, string> = {
  local_ollama: 'setup.detectEngineLocal',
  custom_ollama: 'setup.detectEngineRemote',
  openai_compatible: 'setup.detectEngineCompatible',
}

/**
 * SetupPage — first-run engine choice (end-user onboarding).
 *
 * After installation the user picks their own engine:
 *  - local Ollama (127.0.0.1:11434, detected on this machine and offered)
 *  - remote Ollama (e.g. DGX/LAN — an endpoint of their own)
 *  - OpenAI-compatible (vLLM/SGLang/… — an endpoint of their own)
 *
 * Ephe installs NOTHING and downloads no models — the endpoint is verified by a
 * probe (Ollama: /api/tags, OpenAI: /v1/models), the models it reports are
 * listed for selection, and the choice is persisted to engine.json
 * (via POST /api/settings).
 */

const OPTIONS: { kind: ProviderKind; icon: typeof Cpu; testId: string }[] = [
  { kind: 'local_ollama', icon: Cpu, testId: 'setup-option-local' },
  { kind: 'custom_ollama', icon: Server, testId: 'setup-option-custom' },
  { kind: 'openai_compatible', icon: PlugZap, testId: 'setup-option-openai' },
]

/** R45: quick provider picker — the user usually knows which provider they are
 * on (local Ollama, OpenCode Zen, OpenRouter, DGX/vLLM). One click sets the
 * provider kind plus the endpoint and starts the probe immediately.
 *
 * Decision (n19): the three named rows are DATA about real external services.
 * The label is the service's own public name, the endpoint is the URL its API
 * answers on, and the signup link beside the key field points at the page that
 * service owns. Renaming any of the three breaks the pick, because the probe
 * calls exactly that URL — so they stay as the services spell themselves. The
 * naming rule in AGENTS.md governs the identifiers we author and leaves this
 * data alone: label, endpoint and signup link are another product's public
 * identity, quoted verbatim.
 */
const QUICK_PICKS: { label: string; kind: ProviderKind; endpoint?: string; testId: string }[] = [
  { label: 'Ollama', kind: 'local_ollama', testId: 'setup-quick-ollama' },
  {
    label: 'OpenCode Zen',
    kind: 'openai_compatible',
    endpoint: 'https://opencode.ai/zen/v1',
    testId: 'setup-quick-opencode',
  },
  {
    label: 'OpenRouter',
    kind: 'openai_compatible',
    endpoint: 'https://openrouter.ai/api/v1',
    testId: 'setup-quick-openrouter',
  },
  { label: 'DGX Spark / vLLM', kind: 'openai_compatible', testId: 'setup-quick-dgx' },
]

/** Where a scan suggestion came from: this machine's loopback scan ('scan') or
 *  an address already known to Ephe ('saved' — engine.json, history, env).
 *  R9: the screen names its source instead of labelling both of them "detected". */
function suggestionSource(url: string, candidates?: EngineCandidate[]): 'saved' | 'scan' {
  const key = (url || '').trim().replace(/\/+$/, '')
  const cand = (candidates ?? []).find((c) => (c.url || '').trim().replace(/\/+$/, '') === key)
  return cand?.sweep ? 'scan' : 'saved'
}

/** Order of one class's candidates: a reachable one that has models first, then
 *  the scan order (the user's own address before a loopback find). */
function rankByReachability<T extends { reachable: boolean; models: string[] }>(items: T[]): T[] {
  return [...items].sort(
    (a, b) =>
      Number(b.reachable && b.models.length > 0) - Number(a.reachable && a.models.length > 0),
  )
}

/** W3-26: an engine the scan found, held as an offer for a one-click decision.
 *  Detection never writes into the choice itself — the offer waits for the user's
 *  click (AGENTS.md: the engine belongs to the user, no silent default). */
interface DetectionOffer {
  provider: ProviderKind
  url: string
  models: number
  source: 'saved' | 'scan'
  hint?: string
  hintCode?: string
  keySource?: ProbeKeySource
}

/** S4 (owner decision 2026-10-18): the probe may authenticate with a key found in a
 *  tool beside Ephe, but the screen has to say so — a chat turn reads only Ephe's own
 *  store, so a borrowed answer is one the user cannot keep by clicking through. */
function BorrowedKeyNote({ testId, label }: { testId: string; label: string }) {
  return (
    <p data-testid={testId} className="mt-1.5 text-ui-xs leading-relaxed text-ink-soft">
      {label}
    </p>
  )
}

interface SetupPageProps {
  /** Called once the engine has been persisted (the gate re-checks its status). */
  onDone: () => void
}

export default function SetupPage({ onDone }: SetupPageProps) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<ProviderKind>('local_ollama')
  // The product's own rule: no engine is chosen for the user (AGENTS.md). The state
  // keeps a class for the paths that need one, but the screen shows no selection
  // until a choice exists — made by the user, offered by the scan, or remembered.
  const [chosen, setChosen] = useState(false)
  const choose = (k: ProviderKind) => {
    setKind(k)
    setChosen(true)
  }
  const [endpoint, setEndpoint] = useState('')
  const [probeState, setProbeState] = useState<ProviderProbeResponse | null>(null)
  const [probing, setProbing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [model, setModel] = useState('')
  // T2: the backend refused this start because the stored key belongs to another
  // engine. Put the reason and the four ways out on the screen that repairs it.
  const [repair, setRepair] = useState<SetupRepair | null>(null)
  // The replacement key is typed here: the probe cannot pass while the stored key is
  // wrong, and the repair must not depend on it passing.
  const [repairKey, setRepairKey] = useState('')
  const [repairReplacing, setRepairReplacing] = useState(false)
  // W19: optional authentication for OpenAI-compatible providers — the key stays
  // on this device (server env); Ephe never presets a provider for the user.
  const [apiKey, setApiKey] = useState('')
  // W3-26: what the scan found, held until the user agrees. Null = nothing offered.
  const [offer, setOffer] = useState<DetectionOffer | null>(null)
  // P2: the one-click answer. 'none' means the scan reached no engine this button
  // may persist — the picker below stays the way forward.
  const [oneClick, setOneClick] = useState<'idle' | 'running' | 'none'>('idle')

  const needsUrl = kind !== 'local_ollama'

  // P1-A/P1-B: preferences from the last session (via /api/setup-status).
  const preferredModel = useRef<string>('')
  const preferredEndpoint = useRef<string>('')
  // R9: the last scan (on mount and from the re-scan button) — clicking a remote
  // preset falls back to that instead of inventing a host.
  const scanRef = useRef<DetectResponse | null>(null)
  // The endpoint that the scan/detection itself wrote into the field: only THAT
  // one may be cleared again on a class change — typed user input stays put.
  const suggestedRef = useRef<string>('')
  // Counts every new state write; a probe that arrives after a newer write loses.
  const probeEpoch = useRef(0)
  // Live value of the endpoint field: after waiting, chooseRemotePreset decides
  // against the input as it now stands, not against the closure value from the
  // click — otherwise an address typed during the scan would be erased.
  const endpointRef = useRef('')

  function applyEndpoint(value: string): void {
    endpointRef.current = value
    setEndpoint(value)
  }
  const [suggestion, setSuggestion] = useState<{
    url: string
    source: 'saved' | 'scan'
    hint?: string
    hintCode?: string
  } | null>(null)
  /** A port hint reads in the interface language. The server's own sentence is the
   *  defaultValue, so a code this bundle has no entry for still says something. */
  const portHint = (hint?: string, code?: string) =>
    code ? t(`setup.portHint.${code}`, { defaultValue: hint ?? '' }) : (hint ?? '')
  /** Short engine name inside the offer sentence and over the model list. Literal keys
   *  so the dead-key ratchet in lib/i18n-keys.test.ts can see them. */
  const offerEngine = (k: ProviderKind): string => t(ENGINE_LABEL_KEY[k])
  const [noSuggestionFor, setNoSuggestionFor] = useState<ProviderKind | null>(null)

  async function runProbe(
    overrideKind?: ProviderKind,
    overrideUrl?: string,
    overrideKey?: string,
  ): Promise<void> {
    const k = overrideKind ?? kind
    // R9: result epoch. A late probe of the PREVIOUS class may no longer drive
    // the state — otherwise a delayed "reachable · model X" would land straight
    // on the button that applies the engine.
    const epoch = ++probeEpoch.current
    setProbing(true)
    setError('')
    try {
      const baseUrl =
        k === 'local_ollama' ? '' : (overrideUrl ?? (endpoint.trim() || preferredEndpoint.current))
      const res = await probeProvider(
        k,
        baseUrl || undefined,
        overrideKey ?? (apiKey.trim() || undefined),
      )
      if (epoch !== probeEpoch.current) return
      // R36: structured render — the server detail is German prose
      // ("… erreichbar · N Modelle") and leaked into the English UI; the URL // language-gate: ignore (quoted server prose, built at server/routes/model_provider.py:60 and :121)
      // also duplicated the endpoint field right above. Rebuild the line.
      setProbeState(
        res.reachable
          ? {
              ...res,
              detail: `${res.url ?? baseUrl ?? ''} · ${t('setup.modelsFound', { count: res.models.length })}`,
            }
          : res,
      )
      if (res.reachable && res.models.length > 0) {
        // P1-B: prefer the most recently active model, otherwise the first result.
        const pref = preferredModel.current
          ? res.models.find((m) => m === preferredModel.current)
          : undefined
        // The engine belongs to the user: with more than one model nothing is
        // picked, and the finish button stays where it is until they choose.
        setModel(pref ?? (res.models.length === 1 ? (res.models[0] ?? '') : ''))
      } else {
        setModel('')
      }
    } catch (err) {
      if (epoch !== probeEpoch.current) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (epoch === probeEpoch.current) setProbing(false)
    }
  }

  // P3 (2026-09-15): the shared auto-scan — used on mount and by the re-scan
  // button. In parallel over all candidates (Ollama + DGX/vLLM); the first
  // reachable one with >= 1 model becomes an offer (W3-26) the user can accept.
  async function autoDetect(): Promise<void> {
    // R9: the scan owns the final state — neither an in-flight probe nor a click
    // on a preset may write into it afterwards.
    const epoch = ++probeEpoch.current
    setProbing(true)
    setError('')
    // A fresh scan replaces a pending offer; finding nothing clears it.
    setOffer(null)
    try {
      const res = await detectEngines()
      scanRef.current = res
      if (epoch !== probeEpoch.current) return
      const idx = res.first_reachable
      const hit = idx >= 0 ? res.detected[idx] : undefined
      if (hit && hit.reachable && hit.models.length > 0) {
        if (OPTIONS.some((o) => o.kind === hit.provider)) {
          // W3-26: a hit becomes an offer, never a selection. kind/endpoint/model
          // stay untouched here, so the screen still holds the user's own choice.
          setOffer({
            provider: hit.provider as ProviderKind,
            url: hit.url ?? '',
            models: hit.models.length,
            source: suggestionSource(hit.url ?? '', res.candidates),
            hint: hit.hint,
            hintCode: hit.hint_code,
            keySource: hit.key_source,
          })
          setProbeState(null)
          setModel('')
          return
        }
        // A provider this screen cannot represent has no radio to land on, so it
        // gets no offer; the status line below still runs.
      }
      // No scan hit: fall back to the status line of the active provider.
      const st = await getSetupStatus()
      if (epoch !== probeEpoch.current) return
      if (st.model) preferredModel.current = st.model
      if (st.url) preferredEndpoint.current = st.url
      if (st.provider && OPTIONS.some((o) => o.kind === st.provider))
        choose(st.provider as ProviderKind)
      if (st.url) {
        applyEndpoint(st.url)
        suggestedRef.current = st.url
        setSuggestion({ url: st.url, source: 'saved' })
        setNoSuggestionFor(null)
      }
      if (st.reachable && st.available_models.length > 0) {
        setProbeState({
          reachable: true,
          models: st.available_models,
          detail: `${st.url ?? ''} · ${t('setup.modelsFound', { count: st.available_models.length })}`,
          state: 'ok',
        })
        // The probe rule, applied to the remembered state too: what this device
        // already chose comes back, and only a one-model engine may be filled in.
        const remembered = preferredModel.current
          ? st.available_models.find((m) => m === preferredModel.current)
          : undefined
        setModel(
          remembered ?? (st.available_models.length === 1 ? (st.available_models[0] ?? '') : ''),
        )
      }
    } catch (err) {
      if (epoch !== probeEpoch.current) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (epoch === probeEpoch.current) setProbing(false)
    }
  }

  /** R9: clicking a remote preset must land in a VERIFIED state.
   *
   *  Before: setKind plus setProbeState(null) and nothing else — the click deleted
   *  the auto-detection that had just run and the screen went silent. Now: take
   *  the candidate of THIS class from the user's own scan (engine.json, endpoint
   *  history, env, loopback finds), actually probe it and report the result. If
   *  the class has no candidate, NO host is guessed (AGENTS.md: no silent
   *  default); instead the screen says why nothing can be checked. */
  async function chooseRemotePreset(k: ProviderKind): Promise<void> {
    // A deliberate choice voids everything started before it: otherwise the
    // mount scan still in flight would flip the user's engine class back after
    // the click.
    probeEpoch.current += 1
    // A scheduled typing probe of the old input no longer makes sense.
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    choose(k)
    // State from another class does not count for this one: status, model and
    // message all drop, otherwise "take over" would apply an unverified address.
    setProbeState(null)
    setModel('')
    setError('')
    setSuggestion(null)
    setNoSuggestionFor(null)
    // Choosing a class by hand retires a pending detection offer.
    setOffer(null)

    const atClick = endpointRef.current.trim()
    let scan = scanRef.current
    if (!scan) {
      scan = await detectEngines().catch(() => null)
      if (scan) scanRef.current = scan
    }
    // Whoever types while the scan is running keeps their input: the debounced
    // probe checks it. Suggestions that arrive late never touch the field at all.
    if (endpointRef.current.trim() !== atClick) return
    const hits = rankByReachability(
      (scan?.detected ?? []).filter((d) => d.provider === k && !!d.url),
    )
    const url = hits[0]?.url ?? ''

    if (!url) {
      // Reset only the endpoint the scan itself set — if the user typed their own
      // address, it stays.
      if (!atClick || atClick === suggestedRef.current.trim()) {
        applyEndpoint('')
        suggestedRef.current = ''
      }
      setNoSuggestionFor(k)
      return
    }

    applyEndpoint(url)
    preferredEndpoint.current = url
    suggestedRef.current = url
    setSuggestion({
      url,
      source: suggestionSource(url, scan?.candidates),
      hint: hits[0]?.hint,
      hintCode: hits[0]?.hint_code,
    })
    await runProbe(k, url)
  }

  /** W3-26: "use it" on an offer is the user's consent. It applies the offered
   *  class and endpoint, then verifies them with a live probe — the same path a
   *  preset click takes, so an offer cannot land on an unverified engine. */
  async function acceptOffer(): Promise<void> {
    if (!offer) return
    const k = offer.provider
    const url = offer.url
    // The consent voids anything the scan or a typing probe started before it.
    probeEpoch.current += 1
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    setOffer(null)
    choose(k)
    setProbeState(null)
    setModel('')
    setError('')
    setSuggestion(null)
    setNoSuggestionFor(null)
    if (k === 'local_ollama') {
      applyEndpoint('')
    } else {
      applyEndpoint(url)
      preferredEndpoint.current = url
      suggestedRef.current = url
      setSuggestion({
        url,
        source: offer.source,
        hint: offer.hint,
        hintCode: offer.hintCode,
      })
    }
    await runProbe(k, k === 'local_ollama' ? undefined : url)
  }

  // T2: one status read names why this screen is shown at all. A refused key is a
  // different instruction ("re-enter it") than a first start ("pick an engine").
  useEffect(() => {
    let cancelled = false
    void getSetupStatus()
      .then((status) => {
        const found = status.repair
        if (cancelled || found?.code !== 'engine_key_mismatch') return
        setRepair(found)
        // The engine below is the one the configuration already names; the repair
        // form stays on the engine that has to change.
        const activeKind = found.active.provider as ProviderKind
        if (OPTIONS.some((option) => option.kind === activeKind)) {
          choose(activeKind)
          if (found.active.url) applyEndpoint(found.active.url)
          if (found.active.model) setModel(found.active.model)
        }
      })
      .catch(() => {
        /* the choice still works; the banner is the only loss */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // QD-005B: the companion points at this card, so this screen is the one that
  // says whether it is up. The fact outlives the route — a binding that needs
  // repair does not stop needing one because the user went back to the chat.
  useEffect(() => {
    announceSetupRepair(repair !== null)
  }, [repair])

  // P0-A/P3: auto-scan on mount — parallel multi-engine detection (Ollama +
  // DGX/vLLM). The first reachable candidate with >= 1 model is offered (W3-26).
  useEffect(() => {
    let cancelled = false
    void (async () => {
      if (!cancelled) await autoDetect()
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // P0-B: debounced auto-probe after typing an endpoint (~350ms), with no click
  // on 'Probe endpoint'. The ref holds the value set during mount; only a real
  // user change (endpoint !== ref) triggers the probe.
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    if (!needsUrl || !endpoint.trim()) return
    if (endpoint.trim() === preferredEndpoint.current) return
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      void runProbe()
    }, 350)
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint])

  async function handleFinish() {
    if (!probeState?.reachable || !model) return
    setSaving(true)
    setError('')
    try {
      const key = kind === 'openai_compatible' ? apiKey.trim() : ''
      if (key) {
        // The POST below only reaches the server that answers it. On the desktop the next
        // start spawns its own backend from a launchd environment with no `EPHE_` variable,
        // so the token goes to the shell first and a shell refusal stops the choice here
        // instead of leaving a surface that promises a key the next launch does not have.
        await storeEngineKey(key)
      }
      await updateSettings({
        provider: {
          type: kind,
          model,
          endpoint: needsUrl ? endpoint.trim() : undefined,
          api_key: kind === 'openai_compatible' && apiKey.trim() ? apiKey.trim() : undefined,
        },
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  /** P2: one click, one explicit consent. The scan says which engine answered
   *  and what it serves; the memory the endpoint reports decides which of those
   *  models fits. Nothing is written before this click, and a scan that reaches
   *  no engine writes nothing at all. */
  async function handleOneClick() {
    if (oneClick === 'running' || saving) return
    setOneClick('running')
    setError('')
    try {
      const [scan, mem] = await Promise.all([
        detectEngines(),
        fetch(apiUrl('/api/system/metrics'))
          .then((res) => (res.ok ? res.json() : null))
          .catch(() => null) as Promise<{ mem_total_gb?: number | null } | null>,
      ])
      const totalGb = typeof mem?.mem_total_gb === 'number' ? mem.mem_total_gb : null
      const choice = recommendOneClickSetup(scan.detected, totalGb)
      if (!choice) {
        setOneClick('none')
        return
      }
      setSaving(true)
      await updateSettings({
        provider: {
          type: choice.kind,
          model: choice.model,
          endpoint: choice.kind === 'custom_ollama' ? choice.url || undefined : undefined,
        },
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setOneClick('idle')
      setSaving(false)
    }
  }

  /** T2 choice 1: keep the stored key and restore the engine it is bound to. */
  async function handleKeepBoundEngine() {
    if (!repair?.bound) return
    const boundKind = repair.bound.provider as ProviderKind
    if (!OPTIONS.some((option) => option.kind === boundKind)) return
    setSaving(true)
    setError('')
    try {
      await updateSettings({
        provider: {
          type: boundKind,
          model: repair.bound.model,
          endpoint: repair.bound.url ?? undefined,
        },
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  /** T2 choice 2: keep the engine and enter the key it needs. */
  async function handleRepairKey() {
    if (!repair || !repairKey.trim()) return
    const activeKind = repair.active.provider as ProviderKind
    if (!OPTIONS.some((option) => option.kind === activeKind)) return
    setSaving(true)
    setError('')
    try {
      const key = repairKey.trim()
      // The desktop spawn reads the key file, so the token goes to the shell first;
      // the POST binds it to the engine named here.
      await storeEngineKey(key)
      await updateSettings({
        provider: {
          type: activeKind,
          model: repair.active.model,
          endpoint: repair.active.url ?? undefined,
          api_key: key,
        },
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  async function handleSkip() {
    // W19: skip onboarding — a deliberate choice, not a silent default. The chat
    // stays fail-closed until an engine is chosen; the engine chip in the composer
    // leads back here at any time.
    try {
      await skipSetup()
    } catch {
      // An older server without the skip route: let them through anyway (the gate catches it).
    }
    // Leave the setup route: after the reload the gate (skipped) opens the chat
    // directly — the same route resolution as after handleReset.
    window.location.hash = '#/'
    onDone()
  }

  async function handleReset() {
    // Forget the engine choice (e.g. went back to /chat and wants to choose again)
    await resetSetup().catch(() => {})
    // R25: engine.json is gone, so the gate's answer and its remembered hint are now false.
    // Dropping them here keeps the reload that follows from painting the chat and bouncing
    // back a round trip later.
    forgetSetupGate()
    window.location.hash = '#/'
    window.location.reload()
  }

  const repairBoundKind = repair?.bound ? (repair.bound.provider as ProviderKind) : null
  const canKeepBound =
    repairBoundKind !== null && OPTIONS.some((option) => option.kind === repairBoundKind)
  const reachable = probeState?.reachable === true
  // W18/A5: the probe's three-valued result (ok | busy | unreachable). Without a
  // backend state (older server) the display falls back to reachable/unreachable.
  const engineState: EngineState = probeState?.state ?? (reachable ? 'ok' : 'unreachable')
  /** The picker's rows: the probe's ids with the metadata beside them, grouped under
   *  the engine the user is looking at. An Ollama answer has no metadata and reads as
   *  unknown in every column. */
  const modelRows = useMemo(
    () =>
      probeState
        ? rowsFromProbe(probeState.models, probeState.model_details, t(ENGINE_LABEL_KEY[kind]))
        : [],
    [probeState, kind, t],
  )
  const stateTone: Record<EngineState, string> = {
    ok: 'bg-status-success/10 text-status-success',
    busy: 'bg-status-warning/10 text-status-warning',
    unreachable: 'bg-status-danger/10 text-status-danger',
  }

  return (
    <ErrorBoundary
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background text-foreground/60">
          {t('error.fallback')}
        </div>
      }
    >
      <main
        id="main-content"
        tabIndex={-1}
        className="relative flex min-h-screen flex-col items-center justify-start bg-transparent px-6 py-12"
      >
        <ForestBackground />
        {/* N1-CLS: the card is top-aligned (justify-start in main) instead of
            vertically centred — the top edge stays put when the probe status that
            appears asynchronously changes the card's height. Only the elements
            below the inserted block shift -> minimal CLS. */}
        <div
          className="relative z-sticky w-full max-w-md rounded-2xl border border-hairline bg-surface-raised p-6 backdrop-blur-xl shadow-elevation-1 shadow-black/30"
          data-testid="setup-page"
          id="ephe-chat-input"
          tabIndex={-1}
        >
          <div className="mb-8 text-center">
            {/* S3: 48 px is where the brand contract stops drawing the figure and
                starts showing the shipped render (docs/ONBOARDING_FILM.md). */}
            <HeroMark size="3rem" testId="setup-mark" className="mx-auto mb-4" />
            <div className="mb-3 text-ui-xs uppercase tracking-[0.25em] text-brand/70">
              {t('setup.kicker')}
            </div>
            <h1 className="text-3xl font-medium text-foreground">{t('setup.title')}</h1>
            <p className="mt-2 text-ui-sm text-ink-soft">{t('setup.subtitle')}</p>
          </div>

          {/* P2: the primary path for a first start — one click, one consent. It
              only offers an engine the scan reached on this machine or on an
              endpoint the user already runs, and a model the reported memory
              holds. Everything else stays the picker below. */}
          <div className="mb-5">
            <button
              type="button"
              data-testid="setup-one-click"
              onClick={() => void handleOneClick()}
              disabled={oneClick === 'running' || saving}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-ui-sm font-medium text-black transition-colors hover:bg-brand disabled:opacity-60 pointer-coarse:min-h-11"
            >
              {oneClick === 'running' ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Check className="size-4" aria-hidden />
              )}
              {oneClick === 'running' ? t('setup.oneClickRunning') : t('setup.oneClick')}
            </button>
            <p
              className="mt-2 text-ui-xs leading-relaxed text-ink-soft"
              data-testid="setup-one-click-hint"
            >
              {oneClick === 'none' ? t('setup.oneClickNone') : t('setup.oneClickHint')}
            </p>
          </div>

          {repair && (
            <div
              role="alert"
              data-testid="setup-repair"
              className="mb-5 rounded-xl border border-warning/40 bg-warning/10 p-3"
            >
              <div className="flex gap-2">
                <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
                <div className="min-w-0">
                  <p className="text-ui-sm text-foreground">
                    {t('setup.repairEngineKeyMismatch')}
                  </p>
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-ui-xs">
                    <dt className="text-ink-soft">{t('setup.repairActiveEngine')}</dt>
                    <dd
                      className="truncate font-mono text-foreground"
                      data-testid="setup-repair-active"
                    >
                      {repair.active.provider}/{repair.active.model}
                    </dd>
                    {repair.bound && (
                      <>
                        <dt className="text-ink-soft">{t('setup.repairBoundEngine')}</dt>
                        <dd
                          className="truncate font-mono text-foreground"
                          data-testid="setup-repair-bound"
                        >
                          {repair.bound.provider}/{repair.bound.model}
                        </dd>
                      </>
                    )}
                    <dt className="text-ink-soft">{t('setup.repairKeySource')}</dt>
                    <dd className="text-foreground" data-testid="setup-repair-source">
                      {t(`setup.repairSource.${repair.key_source}`)}
                    </dd>
                  </dl>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {canKeepBound && repair.bound && (
                      <button
                        type="button"
                        data-testid="setup-repair-keep"
                        disabled={saving}
                        onClick={() => void handleKeepBoundEngine()}
                        className="rounded-lg border border-brand/50 bg-brand/15 px-3 py-1.5 text-ui-xs text-foreground hover:bg-brand/25 disabled:opacity-50"
                      >
                        {t('setup.repairKeep', {
                          engine: `${repair.bound.provider}/${repair.bound.model}`,
                        })}
                      </button>
                    )}
                    {repair.active.provider === 'openai_compatible' && (
                      <button
                        type="button"
                        data-testid="setup-repair-replace"
                        aria-expanded={repairReplacing}
                        onClick={() => setRepairReplacing((open) => !open)}
                        className="rounded-lg border border-hairline px-3 py-1.5 text-ui-xs text-foreground hover:bg-surface-raised"
                      >
                        {t('setup.repairReplace')}
                      </button>
                    )}
                    <button
                      type="button"
                      data-testid="setup-repair-cancel"
                      onClick={() => setRepair(null)}
                      className="rounded-lg px-3 py-1.5 text-ui-xs text-ink-soft hover:text-foreground"
                    >
                      {t('setup.repairCancel')}
                    </button>
                  </div>
                  {repairReplacing && repair.active.provider === 'openai_compatible' && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <input
                        type="password"
                        autoComplete="off"
                        data-testid="setup-repair-key"
                        aria-label={t('setup.repairReplace')}
                        value={repairKey}
                        onChange={(event) => setRepairKey(event.target.value)}
                        className="min-w-0 flex-1 rounded-lg border border-hairline bg-surface px-3 py-1.5 font-mono text-ui-xs text-foreground"
                      />
                      <button
                        type="button"
                        data-testid="setup-repair-save"
                        disabled={saving || !repairKey.trim()}
                        onClick={() => void handleRepairKey()}
                        className="rounded-lg border border-brand/50 bg-brand/15 px-3 py-1.5 text-ui-xs text-foreground hover:bg-brand/25 disabled:opacity-50"
                      >
                        {t('setup.repairSave')}
                      </button>
                    </div>
                  )}
                  <p className="mt-2 text-ui-xs text-ink-soft">{t('setup.repairChoose')}</p>
                </div>
              </div>
            </div>
          )}

          {/* W3-26: the scan names what it found and asks. The click is the consent;
              nothing is selected before it. */}
          {offer && (
            <div
              data-testid="setup-offer"
              data-offer-source={offer.source}
              className="mb-5 rounded-xl border border-brand/40 bg-brand/10 p-3"
            >
              <p className="text-ui-sm text-foreground" data-testid="setup-offer-text">
                {offer.source === 'scan'
                  ? t('setup.detectOfferScan', { engine: offerEngine(offer.provider) })
                  : t('setup.detectOfferSaved', { engine: offerEngine(offer.provider) })}
              </p>
              <p className="mt-1 font-mono text-ui-xs text-ink-soft">
                {[offer.url, t('setup.modelsFound', { count: offer.models })]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
              {offer.keySource === 'foreign' && (
                <BorrowedKeyNote
                  testId="setup-offer-borrowed-key"
                  label={t('setup.probeBorrowedKey')}
                />
              )}
              <p className="mt-1 text-ui-xs text-ink-soft">{t('setup.detectConsent')}</p>
              <div className="mt-2.5 flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="setup-offer-use"
                  onClick={() => void acceptOffer()}
                  className="rounded-lg bg-brand px-3 py-1.5 text-ui-xs font-medium text-black transition-colors hover:bg-brand"
                >
                  {t('setup.detectUse')}
                </button>
                <button
                  type="button"
                  data-testid="setup-offer-dismiss"
                  onClick={() => setOffer(null)}
                  className="rounded-lg border border-control px-3 py-1.5 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive"
                >
                  {t('setup.detectDismiss')}
                </button>
              </div>
            </div>
          )}

          {/* R45: quick provider picker — one click = provider + endpoint + probe. */}
          <div
            className="mb-5 flex flex-wrap gap-2"
            role="group"
            aria-label={t('setup.title')}
            data-testid="setup-quick-picks"
          >
            {QUICK_PICKS.map((q) => {
              const active =
                kind === q.kind &&
                (q.endpoint ? endpoint.trim() === q.endpoint : !needsUrl || !endpoint.trim())
              return (
                <button
                  key={q.testId}
                  type="button"
                  data-testid={q.testId}
                  aria-pressed={active}
                  onClick={() => {
                    setOffer(null)
                    choose(q.kind)
                    setError('')
                    if (q.endpoint) {
                      applyEndpoint(q.endpoint)
                      preferredEndpoint.current = q.endpoint
                      suggestedRef.current = q.endpoint
                      setSuggestion(null)
                      setNoSuggestionFor(null)
                      setProbeState(null)
                      // Pass the URL explicitly — state updates are async, the
                      // closure value of `endpoint` would still be stale here.
                      void runProbe(q.kind, q.endpoint, apiKey.trim() || undefined)
                    } else if (q.kind !== 'local_ollama') {
                      // DGX/vLLM without a fixed URL: the same path as a click on
                      // the preset below — a suggestion from the user's own scan,
                      // then a real probe. Blindly probing an empty remote address
                      // only reports "unreachable" instead of getting them further.
                      void chooseRemotePreset(q.kind)
                    } else {
                      // Ollama quick pick: this class IS the machine — no endpoint
                      // needed, the probe takes the local default.
                      applyEndpoint('')
                      setSuggestion(null)
                      setNoSuggestionFor(null)
                      setProbeState(null)
                      void runProbe(q.kind, undefined, apiKey.trim() || undefined)
                    }
                  }}
                  className={`rounded-full border px-3.5 py-1.5 text-ui-xs transition-colors focus-ring ${
                    active
                      ? 'border-brand/50 bg-brand/15 text-brand-deep'
                      : 'border-control bg-surface-raised text-foreground/60 hover:bg-surface-interactive'
                  }`}
                >
                  {q.label}
                </button>
              )
            })}
          </div>

          {/* Engine choice */}
          <div className="mb-5 grid gap-2" role="radiogroup" aria-label={t('setup.title')}>
            {OPTIONS.map(({ kind: k, icon: Icon, testId }) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={chosen && kind === k}
                data-testid={testId}
                onClick={() => {
                  setOffer(null)
                  if (k === 'local_ollama') {
                    choose(k)
                    setProbeState(null)
                    setError('')
                    setSuggestion(null)
                    setNoSuggestionFor(null)
                    void runProbe(k)
                    return
                  }
                  void chooseRemotePreset(k)
                }}
                className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left text-ui-sm transition-colors ${
                  kind === k
                    ? 'border-brand/50 bg-brand/10 text-foreground'
                    : 'border-control bg-surface-raised text-foreground/60 hover:bg-surface-interactive'
                }`}
              >
                <Icon className="h-4 w-4 flex-shrink-0 text-brand" />
                <span className="flex-1">{t(`setup.option.${k}`)}</span>
                {kind === k && <Check className="h-4 w-4 text-brand" />}
              </button>
            ))}
          </div>

          {/* B2: opt-in mirror of the agent tools already on this machine — clicking
              a model prefills provider/endpoint/model, then the normal probe runs.
              Without a derivable endpoint the chip stays purely informative. */}
          <div
            data-testid="setup-environment"
            className="mb-5 rounded-xl border border-hairline bg-surface-raised p-3"
          >
            <p className="mb-2 text-ui-xs font-semibold uppercase tracking-wide text-ink-soft">
              {t('environment.title')}
            </p>
            <EnvironmentTools
              onPick={(pick) => {
                setOffer(null)
                choose(pick.providerKind)
                if (pick.endpoint) {
                  applyEndpoint(pick.endpoint)
                  preferredEndpoint.current = pick.endpoint
                }
                setModel(pick.model)
                setProbeState(null)
                void runProbe(pick.providerKind)
              }}
            />
          </div>

          {/* Endpoint (remote engines only) */}
          {needsUrl && (
            <div className="mb-5">
              <label className="mb-1.5 block text-ui-xs text-ink-soft" htmlFor="setup-endpoint">
                {t('setup.endpointLabel')}
              </label>
              <input
                id="setup-endpoint"
                data-testid="setup-endpoint"
                type="url"
                value={endpoint}
                onChange={(e) => applyEndpoint(e.target.value)}
                placeholder={
                  kind === 'openai_compatible'
                    ? 'http://192.168.1.50:8000/v1'
                    : 'http://192.168.1.50:11434'
                }
                className="w-full rounded-xl border border-control bg-input px-4 py-3 font-mono text-ui-sm text-foreground focus-ring placeholder:text-ink-faint"
              />
              {/* R9: this line says WHERE the value in the field comes from, and
                  when there is nothing to check it says why — instead of staying quiet. */}
              {suggestion && (
                <p
                  data-testid="setup-suggestion"
                  data-suggestion-source={suggestion.source}
                  className="mt-1.5 text-ui-xs text-ink-soft"
                >
                  {suggestion.source === 'scan'
                    ? t('setup.suggestionScan')
                    : t('setup.suggestionSaved')}
                  {suggestion.hint || suggestion.hintCode
                    ? ` · ${portHint(suggestion.hint, suggestion.hintCode)}`
                    : ''}
                </p>
              )}
              {noSuggestionFor && (
                <p data-testid="setup-suggestion-none" className="mt-1.5 text-ui-xs text-ink-soft">
                  {noSuggestionFor === 'custom_ollama'
                    ? t('setup.noEndpointRemote')
                    : t('setup.noEndpointCompatible')}
                </p>
              )}
            </div>
          )}

          {/* Probe */}
          <button
            type="button"
            data-testid="setup-probe"
            onClick={() => void runProbe()}
            disabled={probing || (needsUrl && !endpoint.trim())}
            className="mb-5 flex w-full items-center justify-center gap-2 rounded-xl border border-control bg-surface-raised px-4 py-3 text-ui-sm text-foreground/80 transition-colors hover:bg-surface-interactive disabled:opacity-40"
          >
            {probing ? (
              <Loader2 className="h-4 w-4 animate-spin text-brand" />
            ) : (
              <PlugZap className="h-4 w-4 text-brand" />
            )}
            {t('setup.probe')}
          </button>

          {/* Re-scan: full auto-detect over every candidate (Ollama + DGX/vLLM) */}
          <button
            type="button"
            data-testid="setup-rescan"
            onClick={() => void autoDetect()}
            disabled={probing}
            className="-mt-3 mb-5 flex w-full items-center justify-center gap-2 rounded-xl border border-transparent px-4 py-2 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink-soft disabled:opacity-40"
          >
            {probing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5 text-brand" />
            )}
            {t('setup.rescan')}
          </button>

          {/* Progress — an always-mounted live region: a status mounted together
              with its text is not reliably announced. */}
          <div role="status" aria-live="polite" className="sr-only" data-testid="setup-progress">
            {probing ? t('setup.probing') : saving ? t('setup.saving') : ''}
          </div>

          {/* Status — N1-CLS: a reserved plate (min-h) so that appearing
              asynchronously after the probe cannot shift the finish button. */}
          <div className="min-h-[44px]" role="status" aria-live="polite">
            {probeState && (
              <div
                data-testid="setup-status"
                data-engine-state={engineState}
                className={`mb-5 flex items-start gap-2 rounded-xl px-4 py-3 text-ui-sm ${stateTone[engineState]}`}
              >
                {engineState === 'ok' ? (
                  <Check className="mt-0.5 h-4 w-4 flex-shrink-0" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                )}
                <span>
                  <span className="font-medium" data-testid="setup-engine-state">
                    {t(`setup.engineState.${engineState}`)}
                  </span>
                  {' · '}
                  {probeState.detail}
                </span>
              </div>
            )}
          </div>

          {/* A local engine that answers nothing needs its next step on the
              screen: the installer never installs Ollama and this page never
              pulls a model, so without this line the choice dead-ends here. It
              stays away when the scan already offered an engine, so the screen
              never says "nothing answers" beside "Ollama found". */}
          {kind === 'local_ollama' && !reachable && !offer && (
            <div
              data-testid="setup-local-hint"
              className="mb-5 rounded-xl border border-hairline bg-surface-raised px-4 py-3 text-ui-xs leading-relaxed text-ink-soft"
            >
              <p>{t('setup.localHint')}</p>
              <a
                href="https://ollama.com/download"
                target="_blank"
                rel="noreferrer noopener"
                className="mt-1 inline-block font-medium text-ink-soft underline underline-offset-2 hover:text-foreground"
              >
                {t('setup.localHintLink')}
              </a>
            </div>
          )}

          {/* Model choice — N1-CLS: a reserved plate (min-h) against the select
              line appearing late, only after the probe came back. */}
          <div className="min-h-[64px]">
            {reachable && probeState && probeState.models.length > 0 && (
              <div className="mb-5">
                <label className="mb-1.5 block text-ui-xs text-ink-soft" htmlFor="setup-model">
                  {t('setup.modelLabel')}
                </label>
                <ModelPicker
                  id="setup-model"
                  testId="setup-model"
                  label={t('setup.modelLabel')}
                  placeholder={t('modelPicker.choose')}
                  rows={modelRows}
                  value={model}
                  onChange={setModel}
                />
                {probeState.key_source === 'foreign' && (
                  <BorrowedKeyNote
                    testId="setup-borrowed-key"
                    label={t('setup.probeBorrowedKey')}
                  />
                )}
              </div>
            )}
          </div>

          {/* W19: optional API key for providers that authenticate —
              visible only for openai_compatible, and it stays on this device. */}
          {kind === 'openai_compatible' && (
            <div className="mb-5">
              <label className="mb-1.5 block text-ui-xs text-ink-soft" htmlFor="setup-api-key">
                {t('setup.apiKeyLabel')}
              </label>
              <div className="relative">
                <KeyRound
                  className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint"
                  aria-hidden="true"
                />
                <input
                  id="setup-api-key"
                  data-testid="setup-api-key"
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={t('setup.apiKeyPlaceholder')}
                  className="w-full rounded-xl border border-control bg-input pl-11 pr-4 py-3 font-mono text-ui-sm text-foreground focus-ring placeholder:text-ink-faint placeholder:font-sans"
                />
              </div>
              <p className="mt-1.5 text-ui-xs text-ink-soft">{t('setup.apiKeyHint')}</p>
              {/* The key has to come from the provider; without this line a
                  stranger is left to guess where. */}
              <p
                className="mt-2 text-ui-xs leading-relaxed text-ink-soft"
                data-testid="setup-key-help"
              >
                {t('setup.keyHelp')}{' '}
                <a
                  href="https://openrouter.ai/keys"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  {t('setup.keyHelpOpenrouter')}
                </a>
                {' · '}
                <a
                  href="https://opencode.ai/zen"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  {t('setup.keyHelpOpencode')}
                </a>
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div
              data-testid="setup-error"
              role="alert"
              className="mb-5 rounded-xl bg-status-danger/10 px-4 py-3 text-ui-sm text-status-danger"
            >
              {error}
            </div>
          )}

          {/* Apply */}
          <button
            type="button"
            data-testid="setup-finish"
            onClick={() => void handleFinish()}
            disabled={!reachable || !model || saving}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3.5 text-ui-sm font-medium text-black transition-colors hover:bg-brand disabled:opacity-40"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('setup.finish')}
          </button>

          {/* W19: onboarding can be skipped — a deliberate choice instead of a
              silent default. The chat stays fail-closed until an engine is chosen. */}
          <button
            type="button"
            data-testid="setup-skip"
            onClick={() => void handleSkip()}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border border-control bg-surface-raised px-4 py-2.5 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink-soft"
          >
            {t('setup.skip')}
            <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </button>
          <p className="mt-1.5 text-center text-ui-sm leading-relaxed text-ink-soft">
            {t('setup.skipHint')}
          </p>

          <button
            type="button"
            onClick={() => void handleReset()}
            className="mt-4 w-full text-center text-ui-xs text-ink-soft transition-colors hover:text-ink"
          >
            {t('setup.reset')}
          </button>
        </div>
      </main>
    </ErrorBoundary>
  )
}
