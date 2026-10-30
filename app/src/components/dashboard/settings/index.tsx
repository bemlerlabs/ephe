// SettingsPanel presentation (full page, P6 B6 / ref-16/17/18/20).
'use client'

/**
 * Settings full page (P6 B6) — master-detail like the reference pattern: its own
 * left nav with groups (Basics / Agent capabilities / Data and statistics /
 * Onboard) + `← Back to the task`; on the right H1 + language pill + ? icon,
 * below it the card section of the active tab. Before that a centred dialog; the
 * sections themselves (settings/model.tsx) are unchanged.
 */

import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { m, AnimatePresence } from 'framer-motion'
import { Check, Loader2 } from 'lucide-react'

import SearchInput from '@/components/shell/SearchInput'
import { useSettingsPanelModel, NAV, languageOptions } from './model'
import { RegisterNav } from './registerNav'
import { matchFields, matchRows, matchTabs } from './model/settingsSearch'
import type { SettingsPanelProps, TabKey } from './types'
import { READONLY_TABS } from './types'
import { isDesktopShell } from '@/lib/tauriBridge'

/** Make everything outside the dialog unreachable (P4 finding 5): the siblings
 *  along the ancestor chain get `inert` (keyboard/mouse/AT) and `aria-hidden`
 *  (fallback in engines without inert support). Own, later-opened overlays
 *  (FolderPicker as a body portal) stay untouched. */
function makeBackgroundInert(dialog: HTMLElement): () => void {
  const touched: HTMLElement[] = []
  for (
    let node: HTMLElement | null = dialog;
    node && node !== document.body;
    node = node.parentElement
  ) {
    for (const sib of Array.from(node.parentElement?.children ?? [])) {
      const el = sib as HTMLElement
      if (el === node || el.contains(dialog)) continue
      // A global live region (the Toaster) must stay announceable over the modal;
      // it carries no focusable content that could escape the trap.
      if (el.hasAttribute('data-inert-exempt')) continue
      if (el.hasAttribute('inert') || el.getAttribute('aria-hidden') === 'true') continue
      el.setAttribute('inert', '')
      el.setAttribute('aria-hidden', 'true')
      touched.push(el)
    }
  }
  return () => {
    for (const el of touched) {
      el.removeAttribute('inert')
      el.removeAttribute('aria-hidden')
    }
  }
}

export default function SettingsPanel({ isOpen, onClose, initialTab }: SettingsPanelProps) {
  const model = useSettingsPanelModel({ isOpen, onClose, initialTab })
  const {
    t,
    i18n,
    activeTab,
    deepChanged,
    otherDeepChanged,
    deepSections,
    loading,
    saving,
    saved,
    settingsQuery,
    setSettingsQuery,
    saveSettings,
    selectLanguage,
    panelRef,
    trapPanelFocus,
    section,
  } = model
  const [helpOn, setHelpOn] = useState(false)

  // Measured 2026-10-10: at 390 px the strip shows 4 of its 23 chips, and the active one —
  // the answer to "where am I" — usually stood off-screen. `innerWidth < 768` is where the
  // nav's own `max-md:` utilities break; the optional call survives jsdom, which has no layout.
  useEffect(() => {
    if (!isOpen || window.innerWidth >= 768) return
    document
      .querySelector<HTMLElement>(`[data-testid="settings-nav-${activeTab}"]`)
      ?.scrollIntoView?.({ inline: 'start', block: 'nearest' })
  }, [isOpen, activeTab])

  // Jump feedback for the nav search. A field hit names the register group it lives
  // in, so that group is scrolled into view once its tab has mounted; a tab or row
  // hit only needs the content column at its top. `revealTick` re-runs the reveal
  // when the user clicks the same hit again.
  // G11: inside the open panel, ⌘F / Ctrl+F filters the register. The app's own
  // ⌘F focuses the composer, so this handler takes the event off the window
  // listener before it can fire — otherwise the panel would lose the focus it
  // just set.
  const panelKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'f') {
      const input = panelRef.current?.querySelector<HTMLInputElement>(
        '[data-testid="settings-search"]',
      )
      if (input) {
        e.preventDefault()
        e.stopPropagation()
        e.nativeEvent.stopImmediatePropagation()
        input.focus()
        return
      }
    }
    trapPanelFocus(e)
  }

  const [revealTarget, setRevealTarget] = useState<string | null>(null)
  const [revealTick, setRevealTick] = useState(0)
  const jumpTo = (tab: TabKey, secKey?: string) => {
    model.setActiveTab(tab)
    setRevealTarget(secKey ? `deep-section-${secKey}` : null)
    setRevealTick((n) => n + 1)
  }
  useEffect(() => {
    if (revealTick === 0) return
    // AnimatePresence holds the incoming section until the outgoing one has left,
    // so the group is looked up over frames; the content column is the fallback.
    let frame = 0
    let handle = requestAnimationFrame(function find() {
      const group = revealTarget
        ? document.querySelector<HTMLElement>(`[data-testid="${revealTarget}"]`)
        : null
      if (group || !revealTarget || frame++ > 30) {
        const node = group ?? document.querySelector<HTMLElement>('[data-testid="settings-panel"]')
        node?.scrollIntoView?.({ block: 'start' })
        return
      }
      handle = requestAnimationFrame(find)
    })
    return () => cancelAnimationFrame(handle)
  }, [revealTick, revealTarget])

  // P4 finding 5 — the invoker: the last focus target is remembered while the
  // dialog is CLOSED (focusin pass on window). On closing, focus goes back there,
  // otherwise it would stay on a hidden sidebar button.
  const isOpenRef = useRef(isOpen)
  isOpenRef.current = isOpen
  const invokerRef = useRef<HTMLElement | null>(null)
  useEffect(() => {
    const onFocusIn = (e: FocusEvent) => {
      if (isOpenRef.current) return
      const el = e.target as HTMLElement | null
      if (el && !el.closest('[data-testid="settings-page"]')) invokerRef.current = el
    }
    window.addEventListener('focusin', onFocusIn, true)
    return () => window.removeEventListener('focusin', onFocusIn, true)
  }, [])

  // P4 finding 5 — background inert, initial focus inside the dialog, handback on
  // close. The dialog is the FULL PAGE (header + nav + detail); previously only the
  // detail column carried role="dialog", and its focus trap shut out the back button
  // and the navigation.
  useEffect(() => {
    if (!isOpen) return
    const dialog = panelRef.current
    if (!dialog) return
    const release = makeBackgroundInert(dialog)
    // model/useSettingsState sets the initial focus to the first button; if that is
    // not enough (loading state without a button), focus stays inside the dialog.
    if (!dialog.contains(document.activeElement)) dialog.focus()
    return () => {
      release()
      const invoker = invokerRef.current
      if (invoker && invoker.isConnected) invoker.focus()
    }
  }, [isOpen, panelRef])

  // The footer save surface swaps its button for a confirmation while `saved`
  // holds. Unmounting the focused button dropped the focus onto <body>, outside
  // the dialog — a keyboard-only save then lost the place and the trap had no
  // boundary left to hold. Whichever of the two is mounted reclaims the focus
  // when it was orphaned (not when the user moved on inside the panel).
  const savedRef = useRef<HTMLDivElement>(null)
  const saveBtnRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const panel = panelRef.current
    if (!panel || panel.contains(document.activeElement)) return
    ;(saved ? savedRef : saveBtnRef).current?.focus()
  }, [saved, isOpen, panelRef])

  const query = settingsQuery.trim().toLowerCase()
  const tabHits = matchTabs(NAV, (entry) => t(`settings.${entry.key}`), query)
  const fieldHits = matchFields(deepSections, query, i18n?.language !== 'en')
  // I7-5: rows outside the register (their own endpoint) are the same settings,
  // just not the same source — show both lists together.
  const rowHits = matchRows((k, o) => t(k, o as Record<string, unknown>), query)
  const langLabel =
    languageOptions.find((o) => (i18n?.language || 'de').startsWith(o.code))?.label ??
    i18n?.language
  const nextLangCode = (i18n?.language || 'de').startsWith('de') ? 'en' : 'de'
  return (
    <AnimatePresence>
      {isOpen && (
        <div
          data-testid="settings-page"
          role="dialog"
          aria-modal="true"
          aria-label={t('chat.settings')}
          ref={panelRef}
          tabIndex={-1}
          onKeyDown={panelKeyDown}
          className="fixed inset-0 z-modal bg-background flex flex-col outline-none"
        >
          {/* Header row: ← Back to the task | H1 + language pill | ? icon (ref-16/21).
              All three carry the 24 px touch floor unguarded (W13). */}
          <header className="flex items-center gap-3 px-4 h-12 border-b border-hairline shrink-0">
            <button
              type="button"
              data-testid="settings-back"
              onClick={onClose}
              className="flex items-center gap-1.5 min-h-6 rounded-lg px-2 py-1 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface transition-colors pointer-coarse:min-h-11"
            >
              ← {t('settings.back')}
            </button>
            <div className="flex-1 min-w-0 flex items-center gap-2">
              <h1
                data-testid="settings-title-h1"
                className="text-ui-lg font-semibold text-foreground/90 truncate max-md:sr-only"
              >
                {t(`settings.${activeTab}`)}
              </h1>
              <button
                type="button"
                data-testid="settings-lang-pill"
                onClick={() => void selectLanguage(nextLangCode)}
                aria-label={t('settings.languagePillAria')}
                title={t('settings.languagePillAria')}
                className="rounded-full border border-control bg-surface px-2.5 py-0.5 min-h-6 text-ui-xs text-ink-soft transition-colors hover:text-foreground hover:border-brand/40 pointer-coarse:min-h-11"
              >
                {langLabel}
              </button>
            </div>
            <button
              type="button"
              data-testid="settings-help"
              aria-label={t('settings.help')}
              title={t('settings.help')}
              aria-expanded={helpOn}
              onClick={() => setHelpOn((v) => !v)}
              className="p-1.5 min-w-6 min-h-6 flex items-center justify-center rounded-lg text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface transition-colors pointer-coarse:min-w-11 pointer-coarse:min-h-11"
            >
              ?
            </button>
          </header>
          {helpOn && (
            <p
              data-testid="settings-help-hint"
              className="px-4 py-1.5 text-ui-xs text-ink-faint border-b border-hairline bg-canvas"
            >
              {t('settings.helpHint', { tab: activeTab })}
            </p>
          )}

          {/* Master-detail: nav on the left in groups, card on the right */}
          <div className="flex flex-1 min-h-0 max-md:flex-col">
            <nav
              aria-label={t('settings.title')}
              className="w-52 shrink-0 border-r border-hairline p-2 overflow-y-auto max-md:w-full max-md:flex max-md:flex-col max-md:border-r-0 max-md:border-b max-md:border-hairline"
            >
              {/* I3-V5: search in the navigation — it finds areas and the single
                  setting, and jumps there. That made the expert box redundant.
                  It stays above the chip strip at every width. */}
              <div className="mb-3">
                <SearchInput
                  value={settingsQuery}
                  onChange={setSettingsQuery}
                  placeholder={t('settings.settingsSearchPlaceholder')}
                  label={t('settings.settingsSearch')}
                  testid={'settings-search'}
                />
              </div>
              <RegisterNav
                sections={deepSections}
                query={query}
                tabHits={tabHits}
                fieldHits={fieldHits}
                rowHits={rowHits}
                activeTab={activeTab}
                t={t}
                onJump={jumpTo}
                onSelect={model.setActiveTab}
              />
            </nav>

            <div
              // P4 finding 5: the dialog role belongs on the FULL PAGE (see above) —
              // this column is its content, not a dialog of its own.
              role="region"
              aria-label={t(`settings.${activeTab}`)}
              data-testid="settings-panel"
              className="flex-1 min-w-0 overflow-y-auto px-4 pt-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))]"
            >
              {loading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-5 w-5 animate-spin text-brand/50" />
                </div>
              ) : (
                <AnimatePresence mode="wait">
                  <m.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.15 }}
                  >
                    {section[activeTab]}
                  </m.div>
                </AnimatePresence>
              )}
            </div>
          </div>

          {/* Footer save — DD-24: the only save button on the surface; it writes the
              register (settings.json) and the main block (engine.json). The counter on
              the button carries only what the register reports (`countDeepChanges`);
              the drafts of the main block — workspace path, output path, generation —
              are not counted into it, so the button also stands without a counted
              change. Hiding it would make those drafts unreachable. */}
          {!READONLY_TABS.has(activeTab) &&
            !(activeTab === 'shortcuts' && !isDesktopShell()) &&
            !(activeTab === 'appearance' && otherDeepChanged === 0) && (
              /* Static flex sibling: measured 0 px overlap with the scroll column at 390x844 and
               1280x800. The inset it was missing is the home-indicator band of a notched phone
               running the installed PWA. */
              <div className="px-4 pt-4 pb-[calc(1rem+env(safe-area-inset-bottom))] border-t border-hairline bg-canvas">
                {saved ? (
                  <div
                    ref={savedRef}
                    tabIndex={-1}
                    role="status"
                    data-testid="settings-saved"
                    className="flex h-10 items-center gap-2 text-scale-ui text-ink outline-none"
                  >
                    <Check className="h-4 w-4" />
                    {t('settings.saved')}
                  </div>
                ) : (
                  <div className="flex items-center gap-4">
                    {/* The direction's filled verb: ink on the canvas, square corners,
                      the UI step. The accent stays for what is running now. */}
                    <button
                      ref={saveBtnRef}
                      data-testid="settings-save"
                      onClick={saveSettings}
                      disabled={saving}
                      className="focus-ring inline-flex h-9 items-center gap-2 border border-ink bg-ink px-4 text-scale-ui text-canvas transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 max-lg:min-h-11"
                    >
                      {saving ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                      {t('settings.save')}
                    </button>
                    {/* The count of open changes on the right data axis, where every
                      number of this surface sits. */}
                    {deepChanged > 0 && (
                      <span className="ml-auto flex items-baseline gap-2">
                        <span
                          data-testid="settings-save-changed"
                          className="font-mono text-scale-data tabular-nums text-ink-soft"
                        >
                          {deepChanged}
                        </span>
                        <span className="text-scale-data text-ink-faint">
                          {t('settings.unsavedWord')}
                        </span>
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
        </div>
      )}
    </AnimatePresence>
  )
}
