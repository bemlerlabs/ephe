'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChatMessage } from '@/types'
import { PANEL_STATE_EVENT } from '@/lib/panelEvents'
import { SubagentsTab, MemoryTab, TrajectoryTab, SideConversationTab } from './tabsA'
import { PreviewTab } from './previewTab'
import { ReviewTab, TerminalTab } from './tabsC'
import { FilesTab } from './filesTab'
import { AuditTab } from './auditTab'
import { useTabRegistry } from './useTabRegistry'
import { usePreviewNav } from './usePreviewNav'
import { usePanelGeometry } from './usePanelGeometry'
import { useShellRuns } from './useShellRuns'
import { usePanelPulse } from './usePanelPulse'
import { useTabLabels } from './tabChrome'
import { PanelTabBar } from './panelTabBar'
import { agentTabDomIds } from './tabsTabPill'
import { PanelAddMenu } from './panelAddMenu'
import { PanelEmptyState } from './panelEmptyState'

// I4-1: the seams of the pane live in their own modules — geometry/dock/resize
// (usePanelGeometry), tab registry + persistence (useTabRegistry), the URL pane and
// the PREVIEW_OPEN_EVENT listener (usePreviewNav), agent/user shell runs
// (useShellRuns), the frost pulse (usePanelPulse). The order of these calls is
// part of the contract: it decides the registration order of the effects.
export default function AgentPanel({ messages = [] }: { messages?: ChatMessage[] }) {
  const { t } = useTranslation()
  // Anyone who reduces motion gets the same content without the transition — the
  // toggle stays, the wobble does not.
  const reduceMotion = useReducedMotion()
  const [open, setOpen] = useState(false)

  const { tabState, openTab, closeTab, selectTab, menuOpen, setMenuOpen, tabQuery, setTabQuery } =
    useTabRegistry()
  const {
    panelRef,
    url,
    setUrl,
    draft,
    setDraft,
    nonce,
    inputRef,
    load,
    reload,
    recent,
    pickRecent,
    back,
    forward,
    canBack,
    canForward,
  } = usePreviewNav({ open, setOpen, tabState, openTab })

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // A mask over the pane owns the key: without this line Escape threw the pane
      // shut while the ⌘K palette was still open (measured).
      if (document.querySelector('[role="dialog"],[role="alertdialog"],[aria-modal="true"]')) return
      setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const { dock, width, leftOffset, toggleDock, cycleWidth, fitWidth, onResizeHandleDown } =
    usePanelGeometry(open)

  // Round 5: broadcast the panel state (the header toggles then highlight correctly).
  // Judge page-5 finding 2026-09-07: width/dock travel in the payload so the
  // content column can give the panel width back as padding (a split instead of an
  // overlay — otherwise the send button and the model chips sit under the panel).
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent(PANEL_STATE_EVENT, {
        detail: { open, tab: tabState.active, tabs: tabState.open, width, dock },
      }),
    )
  }, [open, tabState, width, dock])

  const { shellRuns, gitRuns, userRuns, busy, submit } = useShellRuns(messages)
  const labels = useTabLabels({ terminal: shellRuns.length, git: gitRuns.length })
  const pulse = usePanelPulse(open)

  // DD-09: the panel used to start at top:56 and covered the toolbar and the
  // status line on the right (uptime, GB, auto-speak, tok, free). It now sits
  // exactly under the chat chrome — measured against the scroll region (fallback:
  // the bottom edge of the status line), so that mobile's taller toolbar plus
  // checkpoint row is counted in instead of a hardcoded pixel number.
  // (The tab bar is fixed at the panel edge y=0 — no spacer needed anymore.)

  if (!open) return null

  return (
    <m.aside
      ref={panelRef}
      // R2 §4.4: the target node of the active pill — the panel carries
      // role="tabpanel", its id comes from agentTabDomIds (what the pill's
      // aria-controls points at) and it attaches back to the active pill through
      // aria-labelledby. With no open tab (the empty state) id and aria-labelledby
      // drop; the role stays, because even then this surface is the content of
      // this pane.
      role="tabpanel"
      id={tabState.active ? agentTabDomIds.panel(tabState.active) : undefined}
      aria-labelledby={tabState.active ? agentTabDomIds.tab(tabState.active) : undefined}
      aria-label={t('agentPanel.title')}
      initial={{ opacity: 0, x: dock === 'right' ? 24 : -24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      style={{
        width: `min(${width}px, 95vw)`,
        left: dock === 'left' ? leftOffset : undefined,
        top: 0,
        height: '100%',
      }}
      className={`${pulse ? 'frost-pulse-strong' : ''} fixed z-overlay flex flex-col bg-background/95 backdrop-blur-md shadow-elevation-1 ${dock === 'right' ? 'right-0 border-l border-hairline' : 'left-0 border-r border-hairline'}`}
    >
      {/* drag-resize edge (round 12) — the panel's inner edge */}
      <div
        onPointerDown={onResizeHandleDown}
        onDoubleClick={fitWidth}
        data-testid="panel-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label={t('agentPanel.resizeHandle')}
        className={`absolute top-0 h-full w-1.5 cursor-col-resize hover:bg-brand/20 transition-colors z-sticky ${dock === 'right' ? '-left-0.5' : '-right-0.5'}`}
      />
      <PanelTabBar
        tabs={tabState.open}
        active={tabState.active}
        labels={labels}
        dock={dock}
        menuOpen={menuOpen}
        onSelect={selectTab}
        onCloseTab={closeTab}
        onToggleMenu={() => {
          setTabQuery('')
          setMenuOpen((v) => !v)
        }}
        onCollapse={() => setOpen(false)}
        onCycleWidth={cycleWidth}
        onToggleDock={toggleDock}
      />
      {menuOpen && (
        <PanelAddMenu
          tabs={tabState.open}
          active={tabState.active}
          recent={tabState.recent}
          labels={labels}
          query={tabQuery}
          onQuery={setTabQuery}
          onPickTab={(key) => {
            selectTab(key)
            setMenuOpen(false)
          }}
          onCloseTab={closeTab}
          onOpenTab={openTab}
          onDismiss={() => setMenuOpen(false)}
        />
      )}
      <AnimatePresence mode="wait" initial={false}>
        <m.div
          key={tabState.active ?? 'none'}
          className="flex min-h-0 flex-1 flex-col"
          initial={reduceMotion ? { opacity: 1 } : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 1 } : { opacity: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.14, ease: 'easeOut' }}
        >
          {tabState.open.length === 0 ? (
            <PanelEmptyState labels={labels} onOpenTab={openTab} />
          ) : tabState.active === 'preview' ? (
            <PreviewTab
              url={url}
              draft={draft}
              nonce={nonce}
              inputRef={inputRef}
              setDraft={setDraft}
              recent={recent}
              onPickRecent={pickRecent}
              onLoad={load}
              onReload={reload}
              onBack={back}
              onForward={forward}
              canBack={canBack}
              canForward={canForward}
            />
          ) : tabState.active === 'git' ? (
            <ReviewTab />
          ) : tabState.active === 'files' ? (
            <FilesTab
              onOpenFile={(fileUrl) => {
                setUrl(fileUrl)
                setDraft(fileUrl)
                openTab('preview')
              }}
            />
          ) : tabState.active === 'audit' ? (
            <AuditTab />
          ) : tabState.active === 'trajectory' ? (
            <TrajectoryTab />
          ) : tabState.active === 'terminal' ? (
            <TerminalTab runs={[...shellRuns, ...userRuns]} busy={busy} onSubmit={submit} />
          ) : tabState.active === 'subagents' ? (
            <SubagentsTab messages={messages} />
          ) : tabState.active === 'memory' ? (
            <MemoryTab />
          ) : tabState.active === 'side' ? (
            <SideConversationTab />
          ) : null}
        </m.div>
      </AnimatePresence>
    </m.aside>
  )
}
