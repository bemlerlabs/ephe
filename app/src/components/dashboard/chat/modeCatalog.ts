/**
 * The four response modes, in one table: the header control, the plan card and
 * the store's normaliser read it, so a new mode has one place to land.
 *
 * The mode decides what a turn may run (`server/routes/chat.py::_mode_context`:
 * Analyst gets no tools, Architect the read-only ones, Operator all of them,
 * Creator the bundle calls behind a per-session grant). The approval profile is
 * the ceiling above that decision and lives on its own control — a mode pick
 * never writes it, a profile pick never changes the mode.
 */
import { Blocks, ClipboardList, MessageCircle, Terminal, type LucideIcon } from 'lucide-react'

export interface ComposerMode {
  key: string
  /** Hard-coded fallback name when the translation does not resolve (tests, missing key). */
  fallback: string
  hintKey: string
  /** The access the mode grants, rendered as the row's tag. */
  sectionKey: string
  sectionDefault: string
  icon: LucideIcon
}

/** Order == reading direction == keyboard ring. */
export const SESSION_MODES: ComposerMode[] = [
  {
    key: 'analyst',
    fallback: 'Analyst',
    hintKey: 'chat.modeHint.analyst',
    sectionKey: 'chat.modeSection.none',
    sectionDefault: 'Without tools',
    icon: MessageCircle,
  },
  {
    key: 'architect',
    fallback: 'Architect',
    hintKey: 'chat.modeHint.architect',
    sectionKey: 'chat.modeSection.read',
    sectionDefault: 'Read only',
    icon: ClipboardList,
  },
  {
    key: 'operator',
    fallback: 'Operator',
    hintKey: 'chat.modeHint.operator',
    sectionKey: 'chat.modeSection.write',
    sectionDefault: 'With write access',
    icon: Terminal,
  },
  {
    key: 'creator',
    fallback: 'Creator',
    hintKey: 'chat.modeHint.creator',
    sectionKey: 'chat.modeSection.create',
    sectionDefault: 'Creates plugins',
    icon: Blocks,
  },
]

/**
 * The short title of a mode, read from the real hint text: everything before the
 * em dash. If the translation does not resolve (t returns the key) or the separator
 * is missing, the hard-coded fallback name stays.
 */
export function modeShortLabel(mode: ComposerMode, hint: string): string {
  if (!hint || hint === mode.hintKey) return mode.fallback
  const head = hint.split('—')[0]?.trim() ?? ''
  return head && head.length <= 24 ? head : mode.fallback
}

/**
 * The half of the hint that says what the mode does: everything after the em
 * dash. Empty when the translation did not resolve, so a row shows the label
 * alone rather than a sentence that is not there.
 */
export function modeMeaning(mode: ComposerMode, hint: string): string {
  if (!hint || hint === mode.hintKey) return ''
  return hint.split('—').slice(1).join('—').trim()
}
