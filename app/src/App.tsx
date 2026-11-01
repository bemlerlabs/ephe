import { HashRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { domAnimation, LazyMotion, MotionConfig } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { lazy, Suspense, useEffect, useState, useSyncExternalStore } from 'react'
import { ErrorBoundary } from '@/components/ui'
import { Skeleton } from '@/components/ui'
import { Toaster } from '@/components/ui'
import PageErrorBoundary from '@/components/dashboard/PageErrorBoundary'
import { AppShell } from '@/components/shell'
import { useCommandPalette } from '@/hooks'
import { CommandPalette, ConfirmHost } from '@/components/ui'
import { consumeSetupIntent, shouldLeaveSetup } from '@/lib'
import { gateSnapshot, loadSetupGate, subscribeGate, type SetupGate } from '@/lib'

// Route-level code-splitting: chat, setup and memory are independent bundles
const ChatPage = lazy(() => import('./pages/ChatPage'))
const SetupPage = lazy(() => import('./pages/SetupPage'))
// R2-A: memory is its own page, not a strip to the right of the chat.
const MemoryPage = lazy(() => import('./pages/MemoryPage'))
// R4-A2: the workbench is its own page, no longer a pop-up above the chat.
const ArtifactsPage = lazy(() => import('./pages/ArtifactsPage'))
// W4: the tools page carries the vision + session-bundle surfaces.
const ToolsPage = lazy(() => import('./pages/ToolsPage'))
const DiscoverPage = lazy(() => import('./pages/DiscoverPage'))
// W1: the parallel agents and their change sets — the overview the product lacked.
const WorkspacesPage = lazy(() => import('./pages/WorkspacesPage'))
const CustodyPage = lazy(() => import('./pages/CustodyPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))

/**
 * First-run engine gate:
 * configured=true  → chat (the PWA root is the chat dashboard)
 * configured=false → /setup (the user picks their engine: local/remote Ollama,
 *                    OpenAI-compatible — persisted into engine.json)
 * skipped=true     → the user deliberately skipped onboarding (W19):
 *                    gate open, chat fail-closed, setup reachable at any time
 *                    through the engine chip.
 *
 * The status comes from the backend (GET /api/setup/status), not from
 * localStorage — engine.json is the single source of truth (CLI + PWA).
 * Without a backend (serving the static offline build) there is no setup
 * pressure: the gate must never hard-block the app.
 */
function useSetupGate(): SetupGate {
  // R25: the answer is fetched once per app load (lib/setupGate.ts) and shared, so a
  // hash-route change does not re-fetch the gate. The subscription paints whatever is
  // known now — the remembered answer on a repeat load, so the shell is up in the same
  // frame instead of after a round trip.
  const gate = useSyncExternalStore(subscribeGate, gateSnapshot)
  useEffect(() => {
    void loadSetupGate()
  }, [])
  return gate
}

function GateRoute({ children }: { children: React.ReactNode }) {
  const gate = useSetupGate()
  if (!gate.ready) return <RouteFallback />
  // Skip (W19): deliberately skipped onboarding does not block — the chat
  // fails closed with 409 setup_required until an engine has been chosen.
  if (!gate.configured && !gate.skipped) return <Navigate to="/setup" replace />
  return <>{children}</>
}

function SetupGateRoute() {
  // The /setup route is the re-entry into engine setup: it renders the SetupPage
  // when the user explicitly wants it (the engine chip sets an intent —
  // lib/setupGate.ts). Without that intent #/setup is only a hash that survived
  // from an earlier load attempt, and it leads back to the chat instead of
  // leaving the app stuck in first run for good.
  //
  // R25: with a remembered answer (`lib/setupGate.ts`) an already-configured app leaves this
  // route on the first frame, without waiting a round trip to be told what it already knew.
  const gate = useSetupGate()
  const [intent] = useState(() => consumeSetupIntent())
  if (shouldLeaveSetup(gate, intent)) return <Navigate to="/" replace />
  if (!gate.ready) return <RouteFallback />
  return (
    <Suspense fallback={<RouteFallback />}>
      <SetupPage
        onDone={() => {
          // Clear the hash before the reload (the same pattern as handleSkip/
          // handleReset in SetupPage): otherwise '#/setup' survives the reload,
          // the router lands in setup again, and a SUCCESSFUL save looks like a
          // no-op to the user (found 2026-10-01).
          if (window.location.hash === '#/setup') window.location.hash = '#/'
          window.location.reload()
        }}
      />
    </Suspense>
  )
}

/**
 * The route fallback draws the app's own shape (R25 perceived latency).
 *
 * What it replaced, measured 2026-10-14 on the real product server: a centred 32px ring on
 * an empty ground, shown (a) for the whole `GET /api/setup/status` round trip that gates
 * every route, and (b) again for each lazy route chunk. A spinner that says "something is
 * loading" reads as a stall; the same wait behind the shell's own geometry reads as the
 * product arriving. So: skeleton only, no ring — the surface a stranger sees first is the
 * chat they are about to use.
 */
function RouteFallback() {
  return (
    <div
      data-testid="route-skeleton"
      aria-hidden="true"
      className="flex h-full w-full flex-col bg-background"
    >
      {/* The frame is already painted around this skeleton — the rail and the tab bar are
          outside the route table. What is being awaited is the page, so the page is what the
          skeleton draws. */}
      <div className="mx-auto w-full max-w-5xl flex-1 overflow-hidden px-4 py-6">
        <div className="space-y-6">
          <div className="flex justify-end">
            <div className="w-2/3 space-y-2 rounded-2xl glass-reading p-3 sm:w-1/2">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
            </div>
          </div>
          <div className="flex justify-start">
            <div className="w-3/4 space-y-2 rounded-2xl glass-reading p-3 sm:w-2/3">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          </div>
        </div>
        <div className="mt-6 rounded-2xl glass-control p-3">
          <Skeleton className="h-4 w-1/3" />
        </div>
      </div>
    </div>
  )
}

/**
 * W10: a hash the app does not know was rewritten to `/` in silence, so a wrong
 * deep link read as one the app had ignored (FINDINGS.md, 2026-10-12). The notice
 * names the address and offers the chat, inside GateRoute: an old `#/onboarding`
 * bookmark still reaches first-run setup, the case the `*` route exists for.
 */
function UnknownRoute() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  return (
    <GateRoute>
      <div
        data-testid="route-unknown"
        className="flex h-dvh w-full flex-col items-center justify-center gap-3 bg-background p-6 text-center"
      >
        <h1 className="font-display text-ui-lg font-semibold text-foreground">
          {t('route.unknownTitle')}
        </h1>
        <p className="max-w-prose text-ui-sm text-ink-faint">
          {t('route.unknownBody', { path: `#${pathname}` })}
        </p>
        <Link
          to="/chat"
          data-testid="route-unknown-chat"
          className="glass-control focus-ring rounded-xl px-4 py-2 text-ui-sm text-foreground hover:bg-brand/10"
        >
          {t('route.goToChat')}
        </Link>
      </div>
    </GateRoute>
  )
}

/**
 * The data pages (`/memory`, `/artifacts`, `/tools`) share one route shape. The
 * PageErrorBoundary sits inside Suspense and around the page, so both a render
 * crash in the page and a rejected lazy chunk are caught at the page and not at
 * the app root.
 */
function DataRoute({ children }: { children: React.ReactNode }) {
  return (
    <GateRoute>
      <Suspense fallback={<RouteFallback />}>
        {/* The desktop window is transparent, so a data page that paints no ground
            shows the window material behind it. The wrapper owns the ink. */}
        <div className="min-h-full">
          <PageErrorBoundary>{children}</PageErrorBoundary>
        </div>
      </Suspense>
    </GateRoute>
  )
}

// AppInner runs BELOW <Router> in the tree, so useCommandPalette() (which calls
// useNavigate()) sees the Router context. The command palette navigates, so it
// must stay inside the Router provider too.
function AppInner() {
  const { open, query, setQuery, inputRef, grouped, t, setOpen, recordUsage } = useCommandPalette()
  // Note: the Cmd+K handler lives only in the hook (useCommandPalette).
  // A second handler here would toggle the same state twice → the palette would
  // stay closed on every keypress (a double toggle is a no-op).

  return (
    <>
      {/* R33 a11y: keyboard-only path to the primary action. Without this the
          chat input sits behind ~30 tab stops; one Enter lands the caret there. */}
      <a
        href="#ephe-chat-input"
        onClick={(e) => {
          e.preventDefault()
          document.getElementById('ephe-chat-input')?.focus()
        }}
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-modal focus:px-4 focus:py-2 focus:bg-status-success focus:text-black focus:rounded-lg"
      >
        {t('a11y.skipToInput')}
      </a>

      {/* Skip to content link for a11y */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-modal focus:px-4 focus:py-2 focus:bg-status-success focus:text-black focus:rounded-lg"
      >
        {t('a11y.skipToContent')}
      </a>

      {/* G4: the global toaster (toast feedback for errors/offline/updates) */}
      <Toaster />

      {/* Finding #61: one frame for every page — the rail and the tab bar live
          outside the route table, so they do not remount when the page changes. */}
      <AppShell>
        <Routes>
          <Route
            path="/"
            element={
              <GateRoute>
                <Suspense fallback={<RouteFallback />}>
                  <ChatPage />
                </Suspense>
              </GateRoute>
            }
          />
          <Route path="/setup" element={<SetupGateRoute />} />
          <Route
            path="/memory"
            element={
              <DataRoute>
                <MemoryPage />
              </DataRoute>
            }
          />
          <Route
            path="/memory/:view"
            element={
              <DataRoute>
                <MemoryPage />
              </DataRoute>
            }
          />
          <Route
            path="/artifacts"
            element={
              <DataRoute>
                <ArtifactsPage />
              </DataRoute>
            }
          />
          <Route
            path="/artifacts/:view"
            element={
              <DataRoute>
                <ArtifactsPage />
              </DataRoute>
            }
          />
          <Route
            path="/tools"
            element={
              <DataRoute>
                <ToolsPage />
              </DataRoute>
            }
          />
          <Route
            path="/discover"
            element={
              <DataRoute>
                <DiscoverPage />
              </DataRoute>
            }
          />
          <Route
            path="/workspaces"
            element={
              <DataRoute>
                <WorkspacesPage />
              </DataRoute>
            }
          />
          <Route
            path="/workspaces/change/:id"
            element={
              <DataRoute>
                <CustodyPage />
              </DataRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <DataRoute>
                <SettingsPage />
              </DataRoute>
            }
          />
          <Route
            path="/settings/:tab"
            element={
              <DataRoute>
                <SettingsPage />
              </DataRoute>
            }
          />
          <Route
            path="/chat"
            element={
              <GateRoute>
                <Suspense fallback={<RouteFallback />}>
                  <ChatPage />
                </Suspense>
              </GateRoute>
            }
          />
          {/* D7 kept, silence removed (W10): a hash the app no longer knows — an old
            bookmark to the deleted #/onboarding is the case here — still reaches the
            first-run gate through the notice's own GateRoute, and now says which
            address it could not open instead of rewriting it without a word. */}
          <Route path="*" element={<UnknownRoute />} />
        </Routes>
      </AppShell>

      <ConfirmHost />

      <CommandPalette
        open={open}
        query={query}
        setQuery={setQuery}
        inputRef={inputRef}
        grouped={grouped}
        t={t}
        onClose={() => setOpen(false)}
        onSelect={(cmd) => {
          recordUsage(cmd.id)
          cmd.action()
        }}
      />
    </>
  )
}

function App() {
  return (
    <ErrorBoundary>
      {/* One motion limit for the whole surface: framer-motion drops transform
          animations when the operating system asks for calm. Without this line
          every file that imports motion would have to remember it itself —
          four of them had not. */}
      <MotionConfig reducedMotion="user">
        {/* The animation set, chosen once for the whole app. Every surface
            animates with `m` (the core component), which loads the features it
            is given here: enter/exit, hover/tap and viewport. The `motion`
            component was never used, and it carries the drag controls and the
            layout projection engine with it — 128 kB of chunk for two features
            nothing on the surface calls (measured: `m` + `domAnimation` minifies
            13.4 kB gzip smaller than `motion`, on a 41 kB gzip chunk — a cold
            visitor pays it before the first paint, because the shell mounts this
            provider). A surface that later needs drag or layout animation asks
            the root for `domMax` (App.tsx), the same place this one is decided. */}
        <LazyMotion features={domAnimation}>
          <Router>
            <AppInner />
          </Router>
        </LazyMotion>
      </MotionConfig>
    </ErrorBoundary>
  )
}

export default App
