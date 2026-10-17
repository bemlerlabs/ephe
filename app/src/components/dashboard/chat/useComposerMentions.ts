import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { listFs } from '@/lib/api'
import { detectMentionToken, filterMentionEntries, mentionPath } from './composerPopups'

/**
 * F15 (round 14) → P3-3: @ file mentions
 * «@» opens the workspace autocompletion, the selection inserts the path.
 * Detection and filtering are pure logic in chat/composerPopups.ts: «@» as the
 * first character counts the same as «@» after text, and the typed section
 * filters the hits — before, the raw directory listing sat in the list even
 * while the user was already typing. Extracted from ChatInput.tsx.
 *
 * W3-50 walkthrough coherence: the popup's offsets (`start`/`query`) are only
 * valid for the exact text they were detected in. detectMention() runs on every
 * keystroke, but the draft also changes without a keystroke — a voice transcript
 * lands, a slash suggestion is taken over, the wide-research template or a
 * recalled message replaces the text. The cached token then points at the wrong
 * span: the next Enter inserts the path at a stale offset and swallows the send.
 * `detectedInRef` remembers the text the token came from and an effect closes the
 * popup the moment the message no longer matches it.
 */
export function useComposerMentions({
  message,
  setMessage,
  textareaRef,
  workspaceDirRef,
}: {
  message: string
  setMessage: (value: string) => void
  textareaRef: RefObject<HTMLTextAreaElement | null>
  workspaceDirRef: RefObject<string | undefined>
}) {
  const [mention, setMention] = useState<{ query: string; start: number } | null>(null)
  const [mentionItems, setMentionItems] = useState<{ name: string; path: string; type: string }[]>(
    [],
  )
  // P3-3: the highlight starts at row 1 — Enter/Tab insert instead of sending the
  // message (the reviewer produced a junk session «@read» that way).
  const [mentionIndex, setMentionIndex] = useState(0)
  // Out-of-order listFs responses: only the newest request may write.
  const mentionSeqRef = useRef(0)
  // The exact message text the cached token was detected in (see header). Any
  // other draft change leaves it behind and the effect below drops the popup.
  const detectedInRef = useRef<string | null>(null)
  const mentionOpen = mention !== null && mentionItems.length > 0

  useEffect(() => {
    if (mention === null) return
    if (detectedInRef.current === message) return
    // Programmatic draft change (voice / slash pick / template / recall): the
    // token no longer describes the caret, so the popup must not survive it.
    setMention(null)
    setMentionItems([])
  }, [message, mention])

  const detectMention = (text: string, caret: number) => {
    detectedInRef.current = text
    const token = detectMentionToken(text, caret)
    if (!token) {
      setMention(null)
      setMentionItems([])
      return
    }
    mentionSeqRef.current += 1
    const seq = mentionSeqRef.current
    setMention(token)
    setMentionIndex(0)
    const ws = (workspaceDirRef.current ?? '').replace(/\/+$/, '')
    const { dir, segment } = mentionPath(token.query)
    const root = ws ? `${ws}/${dir}`.replace(/\/+$/, '') : dir.replace(/\/+$/, '')
    listFs(root || undefined)
      .then((listing) => {
        // Out-of-order responses: only the newest request writes.
        if (seq !== mentionSeqRef.current) return
        const hits = filterMentionEntries(
          listing.entries.filter((e) => e.type === 'file' || e.type === 'dir'),
          segment,
        ).map((e) => ({
          name: e.name,
          path: root ? `${root}/${e.name}` : e.name,
          type: e.type,
        }))
        setMentionItems(hits)
      })
      .catch(() => {
        if (seq === mentionSeqRef.current) setMentionItems([])
      })
  }

  const applyMention = (item: { path: string; name: string }) => {
    if (!mention) return
    const before = message.slice(0, mention.start)
    const after = message.slice(mention.start + 1 + mention.query.length)
    const insert = item.path.includes(' ') ? `"${item.path}"` : item.path
    setMessage(`${before}${insert} ${after.trimStart()}`)
    setMention(null)
    setMentionItems([])
    textareaRef.current?.focus()
  }

  /** Escape / popup chain: close the @ popup without touching the input text. */
  const dismissMention = useCallback(() => setMention(null), [])

  return {
    mentionOpen,
    mentionItems,
    mentionIndex,
    setMentionIndex,
    detectMention,
    applyMention,
    dismissMention,
  }
}
