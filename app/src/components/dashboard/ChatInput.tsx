import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Command, ShieldCheck, Brain, UploadCloud } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui'
import { getSettings } from '@/lib/api'
import { markSetupIntent } from '@/lib/setupGate'
import { useDeepBool } from '@/lib/deepSettings'
import { type ChatAttachment } from '@/lib/attachments'
import { setComposerDraft } from '@/lib/restartGuard'
import AttachmentPreview from './AttachmentPreview'
import { useChatStore, DEFAULT_COMPOSER_MODE } from '@/store/chatStore'
import ComposerAttachButton from './chat/ComposerAttachButton'
import ComposerFooterHints from './chat/ComposerFooterHints'
import ComposerMentionList from './chat/ComposerMentionList'
import ComposerMicButton from './chat/ComposerMicButton'
import ComposerModeChip from './chat/ComposerModeChip'
import ComposerModelChip from './chat/ComposerModelChip'
import ComposerContextMeter from './chat/ComposerContextMeter'
import ComposerSendButton from './chat/ComposerSendButton'
import ComposerSlashMenu from './chat/ComposerSlashMenu'
import {
  anchorAbove,
  hasModalDialog,
  isInsideOverlay,
  topmostPopup,
  type ComposerPopupKey,
  type MenuPos,
} from './chat/composerPopups'
import { useComposerAttachments } from './chat/useComposerAttachments'
import { useComposerMentions } from './chat/useComposerMentions'
import { useComposerModelSelection } from './chat/useComposerModelSelection'
import { useComposerSendPipeline } from './chat/useComposerSendPipeline'
import { useComposerSlash } from './chat/useComposerSlash'
import { useComposerVoiceInput } from './chat/useComposerVoiceInput'
import { useThinkingChipKey } from './chat/useThinkingChipKey'
import './ChatInput.css'

export type { ChatAttachment }
// P3 wave 2026-10-05: the model entries live in chat/composerModelEntries
// (architecture boundary). The public name stays exported from this file —
// the components/index.ts facade and the N9 tests reach them right here.
export { buildScanEntries, mergeScanEntries } from './chat/composerModelEntries'
export type { ModelChipEntry } from './chat/composerModelEntries'
// P3 wave 2026-10-05: the ring copy lives in chat/contextRing (architecture
// boundary). The public name stays exported from this file — the locales tests
// reach it right here.
export { contextRingLabel } from './chat/contextRing'

interface ChatInputProps {
  onSend: (message: string, attachments?: ChatAttachment[]) => void
  disabled?: boolean
  /** Streaming in progress → the send button turns into a stop button (PWA chat UX plan C1) */
  streaming?: boolean
  onStop?: () => void
  /** Phase F: slash command (/compact, /new, /clear, /help) — the parent parses and runs it. */
  onSlashCommand?: (raw: string) => void
  /** Welcome action-card seed: fills the draft without sending; nonce allows re-filling the same text. */
  draftSeed?: { text: string; nonce: number } | null
  /** E-UX: context utilisation in % (0–100) for the ring around the send button. */
  contextPercent?: number | null
  /** F3: the same occupancy in tokens, for the meter beside the ring. */
  contextTokens?: { used: number; window: number } | null
}

/** G-A → 2026 IA sweep → P3 wave 2026-10-05: the four composer modes live in
 *  chat/ComposerModeMenu (sections + short title taken from the real hint text).
 *  The active mode mirrors the security profile; 'ask' is the conservative mode,
 *  and DEFAULT_COMPOSER_MODE decides what a fresh session starts on. */

export default function ChatInput({
  onSend,
  disabled = false,
  streaming = false,
  onStop,
  onSlashCommand,
  draftSeed = null,
  contextPercent = null,
  contextTokens = null,
}: ChatInputProps) {
  const { t } = useTranslation()
  // I6-3: `chat.allow_input_while_streaming` — off makes Enter useless during an
  // answer and the field read-only; the composer stays readable, only the queue
  // disappears (the queue was so far the only behaviour).
  const allowInputWhileStreaming = useDeepBool('chat.allow_input_while_streaming', true)
  // D2: the queue wording is only true while the composer can hand work over.
  // With `disabled` set the send pipeline returns before it enqueues, so the
  // busy wording is the honest one there.
  const queueRuns = streaming && allowInputWhileStreaming && !disabled
  const composerPlaceholder = !streaming
    ? t('chat.placeholder')
    : queueRuns
      ? t('chat.queuePlaceholder')
      : t('chat.busyPlaceholder')
  const [message, setMessage] = useState('')
  // F1: the composer states no rule. A blank draft disables send; the field's
  // own label and the button's label still name the controls for a reader.
  // M3 (reference pattern): amber permission badge driven by the security profile.
  const [perm, setPerm] = useState('strict')
  // G-A (reference parity): interactive mode selector — Ask / Edit auto / Plan / Full access.
  // W19: the mode is a session attribute (IndexedDB + server mirror) — it survives
  // reload/session switches instead of dropping back to 'ask' on every unmount.
  // typeof guard: storeMode is a string|undefined (real store); only adopt it when
  // it is one, otherwise old store mocks without a selector re-render forever here.
  const activeSessionId = useChatStore((s) => s.activeSessionId)
  const storeMode = useChatStore((s) => s.sessions.find((x) => x.id === s.activeSessionId)?.mode)
  const [mode, setModeState] = useState<string>(() =>
    typeof storeMode === 'string' && storeMode ? storeMode : DEFAULT_COMPOSER_MODE,
  )
  useEffect(() => {
    if (typeof storeMode === 'string' && storeMode) setModeState(storeMode)
  }, [activeSessionId, storeMode])
  // Pop-up menu state for the mode selector (consistent with the model-chip pattern).
  const [modeOpen, setModeOpen] = useState(false)
  // P6 (ref-23): the plus menu bundles file/image/screenshot attachments
  const [attachOpen, setAttachOpen] = useState(false)
  // W19 → P3 wave 2026-10-05: composer menus as a body portal — the overhang into
  // the welcome area (panel-chat, overflow-y-auto) was clipped by that container,
  // and the absolute plus menu sat BEHIND the composer window (the first two items
  // were unreachable). All three menus now portal to the body, clip-immune; the
  // position comes from the chip rect, opens upward and is pulled back
  // horizontally into the viewport (ComposerMenu).
  const modeChipRef = useRef<HTMLButtonElement | null>(null)
  const attachChipRef = useRef<HTMLButtonElement | null>(null)
  const [modeMenuPos, setModeMenuPos] = useState<MenuPos | null>(null)
  const [attachMenuPos, setAttachMenuPos] = useState<MenuPos | null>(null)
  const syncMenuPos = useCallback((el: HTMLElement | null, set: (pos: MenuPos) => void) => {
    if (!el) return
    set(anchorAbove(el.getBoundingClientRect()))
  }, [])
  const syncModeMenuPos = useCallback(() => {
    syncMenuPos(modeChipRef.current, setModeMenuPos)
  }, [syncMenuPos])
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const workspaceDirRef = useRef<string | undefined>(undefined)

  // Welcome action cards seed the draft through the parent; the parent-owned
  // nonce lets the same text be filled again after the user cleared it.
  useEffect(() => {
    if (draftSeed && draftSeed.nonce > 0) setMessage(draftSeed.text)
  }, [draftSeed])

  // The restart guard reads the live draft from here: a relaunch that arrives
  // with unsent text in this field would take that text with it. The cleanup
  // clears the published draft when the composer leaves the tree.
  useEffect(() => {
    setComposerDraft(message)
  }, [message])
  useEffect(() => () => setComposerDraft(''), [])

  // EPHE-UI-001 (P0): composer auto-grow — the textarea grows with its content up
  // to max-h-32 (~8 lines), then scrolls internally. Otherwise rows={1} pins the
  // height to a single line (parity gap versus the reference clients: multi-line
  // prompts are effectively invisible while editing).
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`
  }, [message])

  // K3 Z24 / W19 / P1-10: model + provider selection (chip state, provider list,
  // setup re-entry, live-provider switch) — see chat/useComposerModelSelection.
  const {
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
  } = useComposerModelSelection()

  useEffect(() => {
    getSettings()
      .then((s) => {
        workspaceDirRef.current = (s as { workspace_dir?: string }).workspace_dir
        const p = (s as { approval_profile?: string }).approval_profile
        if (p) setPerm(p)
      })
      .catch(() => {})
  }, [])

  // G1.3/DD-01: send pipeline — draft history/recall, the Alt+Enter queue and
  // the stream-settle auto-flush — see chat/useComposerSendPipeline.
  const { handleSend, queueCount, recall, recallPrev, recallNext, resetRecall, enqueueCurrent } =
    useComposerSendPipeline({
      disabled,
      streaming,
      allowInputWhileStreaming,
      message,
      setMessage,
      attachments,
      setAttachments,
      onSend,
      onSlashCommand,
    })

  // Phase F + R33/R34: slash autocompletion (menu data + keyboard ring) —
  // see chat/useComposerSlash. `handleSend` lets the exact-command Enter send.
  const {
    slashAppHits,
    slashSkillHits,
    slashFlat,
    slashIndex,
    setSlashIndex,
    setSlashDismissed,
    slashOpen,
    applySuggestion,
    confirmSlash,
  } = useComposerSlash({ message, setMessage, textareaRef, handleSend })

  // F15 (round 14) → P3-3: @ file mentions — see chat/useComposerMentions.
  const {
    mentionOpen,
    mentionItems,
    mentionIndex,
    setMentionIndex,
    detectMention,
    applyMention,
    dismissMention,
  } = useComposerMentions({ message, setMessage, textareaRef, workspaceDirRef })

  // R18: voice input (record → transcribe → draft) — see chat/useComposerVoiceInput.
  const { recording, transcribing, micFrame, micLevelsRef, onMicPointerDown, onMicPointerUp } =
    useComposerVoiceInput({ setMessage, textareaRef })

  // ── P3 wave 2026-10-05: ONE escape chain for all composer popups ────────
  // The overlay promises «Esc — Panel / Dialog schließen · Generierung // language-gate: ignore — quoted shortcut-overlay copy, app/src/locales/de.json:1297 close (the shipped text reads «Ephes Computer», not «Panel»)
  // stoppen». <!-- language-gate: ignore (quoted shortcut-overlay copy, app/src/locales/de.json:1297) --> Order (chat/composerPopups.ts): palette/dialog > model menu >
  // mode menu > plus menu > @ popup > slash list. Only when nothing is open
  // anymore does Escape stop generation.
  const popupsOpen: Record<ComposerPopupKey, boolean> = useMemo(
    () => ({
      model: chipOpen,
      mode: modeOpen,
      attach: attachOpen,
      mention: mentionOpen,
      slash: slashOpen,
    }),
    [chipOpen, modeOpen, attachOpen, mentionOpen, slashOpen],
  )
  const closePopup = useCallback(
    (which: ComposerPopupKey) => {
      if (which === 'model') setChipOpen(false)
      else if (which === 'mode') setModeOpen(false)
      else if (which === 'attach') setAttachOpen(false)
      else if (which === 'mention') dismissMention()
      else if (which === 'slash') setSlashDismissed(true)
    },
    [setChipOpen, dismissMention, setSlashDismissed],
  )
  /** Close the topmost open popup; true = Escape was consumed. */
  const closeTopPopup = useCallback((): boolean => {
    const top = topmostPopup(popupsOpen)
    if (!top) return false
    closePopup(top)
    return true
  }, [popupsOpen, closePopup])

  // P0-3 («ESC-cancel») merged with U1b: one listener for the popup chain and the
  // stream abort, so the same order applies — at idle as well as while streaming.
  useEffect(() => {
    const anyOpen = topmostPopup(popupsOpen) !== null
    if (!streaming && !anyOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // Palette / dialog / menu belongs to whoever opened it: that side closes it.
      if (hasModalDialog() || isInsideOverlay(document.activeElement)) return
      if (closeTopPopup()) {
        e.preventDefault()
        return
      }
      if (!streaming) return
      e.preventDefault()
      onStop?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [streaming, popupsOpen, closeTopPopup, onStop])

  // P1-4: drag & drop / paste / plus-menu attachment mechanics — see
  // chat/useComposerAttachments. Declared AFTER the escape chain so the original
  // window-listener order (escape before drag) stays intact.
  const {
    dragOver,
    fileInputRef,
    imageInputRef,
    addFiles,
    handlePaste,
    handleAttach,
    handleCaptureScreen,
  } = useComposerAttachments({ setAttachments })

  // P3-6: thinking status (hook here, not in the JSX — rules of hooks).
  const thinkingChipKey = useThinkingChipKey()

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // W10-P1-1: IME guard — while a composition (CJK input) is running, Enter fires
    // as the composition commit, not as a send; the native isComposing signal
    // suppresses the send paths. (React 19 does not copy the field onto the
    // SyntheticEvent — read it off the nativeEvent.)
    if (e.nativeEvent.isComposing) return
    // P3-3: the @ popup is fully keyboard-operable — the arrows move the highlight
    // (from row 1), Enter/Tab insert the file, Escape closes the hit and leaves
    // the typed text untouched.
    if (mentionOpen) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const n = mentionItems.length
        setMentionIndex((i) => (i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        dismissMention()
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        applyMention(mentionItems[Math.min(mentionIndex, mentionItems.length - 1)]!)
        return
      }
    }
    // R33: full keyboard control of the slash menu — ArrowUp/Down walk the
    // highlighted row, Escape dismisses the popup (keystroke stays in the
    // input), Enter/Tab picks the highlighted suggestion.
    if (slashOpen) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const n = slashFlat.length
        setSlashIndex((i) => (i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setSlashDismissed(true)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        confirmSlash(slashFlat[Math.min(slashIndex, slashFlat.length - 1)])
        return
      }
    }
    // ↑ — recall an older message (only without Shift)
    if (e.key === 'ArrowUp' && !e.shiftKey) {
      e.preventDefault()
      recallPrev(message)
      return
    }
    // ↓ — recall a newer message
    if (e.key === 'ArrowDown' && !e.shiftKey) {
      e.preventDefault()
      recallNext()
      return
    }
    // Escape — the topmost popup closes first (plus/mode/model: focus is still in
    // the text field here), only after that does the recall reset.
    if (e.key === 'Escape') {
      if (closeTopPopup()) {
        e.preventDefault()
        return
      }
      resetRecall()
      return
    }
    // Alt+Enter — put it in the queue instead of sending
    if (e.key === 'Enter' && e.altKey) {
      e.preventDefault()
      enqueueCurrent()
      return
    }
    // I6 P1-3: the earlier second slash block (Phase F) was redundant and still
    // intercepted Enter after an Escape dismissal (slashDismissed=true), replacing
    // the input — the R33 block above is the only guard.
    // Enter (without Shift/Alt) — send
    if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Command button: open the Cmd+K palette (G3: no dead button)
  const openPalette = () => {
    const isMac = /Mac|iPhone|iPad/.test(navigator.userAgent)
    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'k',
        metaKey: isMac,
        ctrlKey: !isMac,
      }),
    )
  }

  return (
    <div className="px-4 pb-4 mx-auto w-full max-w-3xl">
      {dragOver &&
        createPortal(
          <div
            data-testid="viewport-drop-overlay"
            className="fixed inset-0 z-modal flex items-center justify-center bg-canvas/60 backdrop-blur-[2px] pointer-events-none"
          >
            <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-brand/60 bg-forest-deep/85 px-10 py-8 text-center shadow-elevation-2">
              <UploadCloud className="h-8 w-8 text-brand" />
              <p className="text-ui-sm font-medium text-foreground">{t('chat.dropToAttach')}</p>
              <p className="text-ui-xs text-ink-soft">{t('chat.dropToAttachHint')}</p>
            </div>
          </div>,
          document.body,
        )}
      <div
        className={`glass-control composer-dock rounded-2xl p-3 transition-all duration-base ${dragOver ? 'ring-2 ring-brand/60' : ''}`}
      >
        {/* F15 → P3-3: @ mentions (listbox, keyboard ring from row 1) */}
        {mentionOpen && (
          <ComposerMentionList
            items={mentionItems}
            activeIndex={mentionIndex}
            onPick={applyMention}
          />
        )}
        {slashOpen && (
          <ComposerSlashMenu
            appHits={slashAppHits}
            skillHits={slashSkillHits}
            activeCmd={slashFlat[slashIndex]?.cmd}
            onPick={applySuggestion}
          />
        )}
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => {
            setMessage(e.target.value)
            detectMention(e.target.value, e.target.selectionStart ?? e.target.value.length)
          }}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={composerPlaceholder}
          aria-label={composerPlaceholder}
          readOnly={streaming && !allowInputWhileStreaming}
          id="ephe-chat-input"
          data-testid="chat-input"
          // A dash the user typed is a dash: WKWebView's smart substitution
          // turned `--flag` into an em dash before the model ever saw it.
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          aria-expanded={slashOpen || mentionOpen}
          aria-controls={mentionOpen ? 'mention-listbox' : 'slash-menu'}
          aria-activedescendant={
            mentionOpen && mentionItems.length > 0
              ? `mention-opt-${Math.min(mentionIndex, mentionItems.length - 1)}`
              : slashOpen && slashFlat[slashIndex]
                ? `slash-opt-${slashFlat[slashIndex].cmd}`
                : undefined
          }
          className="w-full bg-transparent text-foreground placeholder:text-ink-faint resize-none outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 text-ui-input min-h-[48px] max-h-32"
          rows={1}
        />
        <div
          className="flex flex-wrap max-sm:flex-nowrap items-center justify-between gap-x-2 gap-y-2 max-sm:gap-x-1 mt-2"
          data-testid="composer-actions-row"
        >
          {/* G3: hidden file inputs (browser path; Tauri uses the native picker) */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              void addFiles(e.target.files)
              e.target.value = ''
            }}
          />
          <input
            ref={imageInputRef}
            type="file"
            multiple
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              void addFiles(e.target.files)
              e.target.value = ''
            }}
          />
          <div className="flex min-w-0 flex-wrap max-sm:flex-nowrap items-center gap-1 max-lg:gap-2">
            {/* P6 (ref-23): ONE plus for all attachments — file/image/screenshot
                live in the menu, the main row stays narrow. */}
            <ComposerAttachButton
              open={attachOpen}
              anchorRef={attachChipRef}
              menuPos={attachMenuPos}
              onToggle={() => {
                setAttachOpen((v) => !v)
                syncMenuPos(attachChipRef.current, setAttachMenuPos)
              }}
              onClose={() => setAttachOpen(false)}
              onAttachFile={() => handleAttach()}
              onAttachImage={() => handleAttach('image')}
              onCaptureScreen={() => void handleCaptureScreen()}
              onWideResearch={() => {
                setMessage(t('chat.wideResearchTemplate'))
                textareaRef.current?.focus()
              }}
            />
            {/* M3/G-A (reference pattern): interactive mode selector as a pop-up menu
                (like the model chip) — compact, one chip + a dropdown picker. */}
            <ComposerModeChip
              open={modeOpen}
              mode={mode}
              approval={perm}
              anchorRef={modeChipRef}
              menuPos={modeMenuPos}
              onToggle={() => {
                setModeOpen((v) => !v)
                syncModeMenuPos()
              }}
              onClose={() => setModeOpen(false)}
              onPick={(key) => {
                setModeState(key)
                if (activeSessionId) {
                  const store = useChatStore.getState() as unknown as {
                    setSessionMode?: (id: string, mode: string) => void
                  }
                  store.setSessionMode?.(activeSessionId, key)
                }
                setModeOpen(false)
              }}
            />
            {mode === 'ask' && (
              <span
                className="hidden md:inline text-ui-xs text-ink-faint whitespace-nowrap"
                title={t('chat.askNoTools')}
                data-testid="composer-ask-hint"
              >
                {t('chat.askNoTools')}
              </span>
            )}
            {/* F2: the chip above states the mode; this states who approves. */}
            <span
              data-testid="composer-permission-badge"
              role="status"
              aria-label={`${t('chat.permissionAria', { defaultValue: 'Approvals' })}: ${String(t(`chat.perm.${perm}`))}`}
              title={t(`chat.perm.${perm}`)}
              className="inline-flex items-center gap-1 rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ui-xs text-status-warning shrink-0 max-lg:min-h-11 max-lg:max-w-20 max-sm:hidden overflow-hidden"
            >
              <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span className="truncate min-w-0">{t(`chat.perm.${perm}`)}</span>
            </span>
            {/* WP2b keep: the dot reports the engine's real offline capability. */}
            <span
              data-testid="composer-status-dot"
              role="img"
              aria-label={
                offlineCapable ? t('chat.offlineCapableLocal') : t('chat.offlineCapableRemote')
              }
              title={
                offlineCapable ? t('chat.offlineCapableLocal') : t('chat.offlineCapableRemote')
              }
              className={`h-1.5 w-1.5 rounded-full shrink-0 ${offlineCapable ? 'bg-status-success' : 'bg-mist/40'}`}
            />
            {/* P6 (ref-23): the image/screenshot/file buttons live in the plus menu —
                the main row stays reduced to the slim anatomy. */}
            {typeof navigator.mediaDevices?.getUserMedia === 'function' && (
              <span className="inline-flex max-sm:hidden">
                <ComposerMicButton
                  recording={recording}
                  transcribing={transcribing}
                  micFrame={micFrame}
                  micLevelsRef={micLevelsRef}
                  onPointerDown={onMicPointerDown}
                  onPointerUp={onMicPointerUp}
                />
              </span>
            )}
            <button
              onClick={openPalette}
              aria-label={t('chat.openPalette')}
              className="p-2.5 rounded-lg shrink-0 hover:bg-brand/10 text-ink-soft hover:text-brand transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 max-lg:min-w-11 max-lg:min-h-11 max-sm:hidden"
            >
              <Command className="h-4 w-4" />
            </button>
          </div>
          {/* M3 (reference pattern): model chip + thinking chip + send in one
              right-hand group — like the reference composer pattern. */}
          <div className="relative flex min-w-0 shrink-0 items-center gap-2 ml-auto max-sm:max-w-[8rem] max-sm:overflow-hidden">
            <ComposerContextMeter
              percent={contextPercent}
              used={contextTokens?.used ?? null}
              window={contextTokens?.window ?? null}
              onCompact={() => onSlashCommand?.('/compact')}
            />
            <ComposerModelChip
              open={chipOpen}
              anchorRef={modelChipRef}
              menuPos={modelMenuPos}
              needsSetup={needsSetup}
              model={model}
              providers={providers}
              activeP={activeP}
              onToggle={() => {
                setChipOpen((v) => !v)
                syncModelMenuPos()
              }}
              onClose={() => setChipOpen(false)}
              onPick={pickProvider}
              onSetup={() => {
                setChipOpen(false)
                markSetupIntent()
                window.location.hash = '#/setup'
              }}
            />
            {/* P3-6: thinking status — pure status, NOT a switch: thinking cannot be
                toggled in the composer (the engine mode decides), this row only
                observes the session. Hence no switch look (no border, no
                background), but a title and the full name. */}
            <span
              data-testid="composer-thinking-chip"
              role="status"
              aria-label={`${String(t('chat.thinkingChipAria'))}: ${String(t(thinkingChipKey))}`}
              title={t('chat.thinkingChipHint', {
                defaultValue:
                  'Shows whether Ephe already thought along in this task — status only, not a switch',
              })}
              className="inline-flex items-center gap-1 px-1 py-0.5 text-ui-xs text-ink-faint shrink-0 max-lg:min-h-11 max-lg:px-1 max-sm:hidden"
            >
              <Brain className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span>{t(thinkingChipKey)}</span>
            </span>
            <ComposerSendButton
              streaming={streaming}
              sendDisabled={disabled || (!streaming && !message.trim())}
              onSend={handleSend}
              onStop={onStop}
              contextPercent={contextPercent}
              queueCount={queueCount}
            />
          </div>
        </div>
        <AttachmentPreview
          attachments={attachments}
          onRemove={(i) => setAttachments((prev) => prev.filter((_, idx) => idx !== i))}
        />
      </div>
      <ComposerFooterHints recall={recall} queueCount={queueCount} />
      {/* M3: the model chip lives in the action row (reference pattern); all that is
          left here is the offline hint as a cap underneath — ONLY when it is
          informative (finding 2026-10-01: the always-visible «Remote engine» chip
          looked orphaned and duplicated the status bar + model chip).
          Render only after the provider answers (no local-default flash). */}
      {offlineCapable && activeP !== '' && (
        <div className="flex items-center justify-center gap-2 mt-2">
          <Badge variant="success">{engineLabel}</Badge>
        </div>
      )}
    </div>
  )
}
