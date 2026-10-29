import { create } from 'zustand'
import {
  type ChatState,
  type StoreCtx,
  makePersistActive,
  makeSetTransientMeta,
  makeMarkSandboxStatus,
  makeSessionActions,
  makeStreamActions,
  makeHelperActions,
  makeToolActions,
  makeCheckpointActions,
} from './chat'

/**
 * Chat store (facade). The body is split 1:1 across ./chat/*:
 *   types.ts        — ChatState, StoreCtx, SetFn/GetFn, ToolCallModel
 *   helpers.ts      — toDbSession, fromDbSession, updateActiveMessage,
 *                     closeThinkingPhases, indicatorMessage, deriveSessionTitle, defaults
 *   sessionModel.ts — Z53: tags / folders / trash — shapes, field operations,
 *                     the persisted-shape migration (sessionModel.ts, no store, no IO)
 *   persist.ts      — makePersistActive, makeSetTransientMeta, makeMarkSandboxStatus
 *   session.ts      — makeSessionActions (load, send, compact, branch, edit)
 *   stream.ts       — makeStreamActions (in-place streaming, TTFT, thinking phases)
 *   helper.ts       — makeHelperActions (visibility: the helper as its own session)
 *   tools.ts        — makeToolActions (tool-call upserts, activities, sandbox tokens)
 *   checkpoints.ts  — makeCheckpointActions (P2-7)
 */
export const useChatStore = create<ChatState>((set, get) => {
  const setFn = set as unknown as import('./chat').SetFn
  const getFn = get as unknown as import('./chat').GetFn
  const persistActive = makePersistActive(getFn)
  const setTransientMeta = makeSetTransientMeta(setFn)
  const baseCtx = { set: setFn, get: getFn, persistActive, setTransientMeta }
  const ctx: StoreCtx = {
    ...baseCtx,
    markSandboxStatus: makeMarkSandboxStatus(baseCtx as StoreCtx),
  }
  return {
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    hydrated: false,
    checkpoints: {},
    lastTurnUsage: null,
    budgetNotice: null,
    solInsights: [],
    enginePricing: null,
    setEnginePricing: (p) => set({ enginePricing: p }),
    ...makeSessionActions(setFn, getFn, persistActive),
    ...makeStreamActions(ctx),
    ...makeHelperActions(setFn, getFn),
    ...makeToolActions(ctx),
    ...makeCheckpointActions(ctx),
  } as ChatState
})

export type { ChatState, ChatStore, ChatMessage, ToolCall, PendingToolCall } from './chat'
export { DEFAULT_SESSION_TITLE, DEFAULT_COMPOSER_MODE } from './chat'

/**
 * `window.__epheStore` — the store handle the dev-only specs seed through.
 *
 * It exists because seeding real state (a 120-message session, a message with
 * thinking blocks and tool calls) through the UI is not what those specs are
 * about: they check the *rendered* surface against the store's own numbers —
 * the status chip against `getState().sessions.length`, the plan card against a
 * seeded message, the virtualization bound against 120 seeded rows. Without a
 * handle they cannot seed at all, so `hasDevHandle` in the specs' helpers asks
 * for exactly this name. The capture and sichtcheck scripts of the same family
 * (`app/capture_*_r36*.mjs`, `scripts/sichtcheck_w1*.mjs`) read it too.
 *
 * Only the dev path defines it: `import.meta.env.DEV` is replaced by `false` in
 * a production build, so this branch is dead code there and the assignment never
 * reaches the shipped bundle — which is why `hasDevHandle` keeps skipping those
 * specs on the static-dist CI leg, where the bundle is the product. Exposing a
 * writable store on `window` in a build that users run is a capability the
 * console did not have (every action, including the sandbox-approval ones, would
 * be reachable from any script in the page); the dev lane is where it belongs.
 */
if (import.meta.env.DEV && typeof window !== 'undefined') {
  ;(window as unknown as { __epheStore?: typeof useChatStore }).__epheStore = useChatStore
}
