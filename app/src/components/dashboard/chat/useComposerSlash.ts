import { useEffect, useMemo, useState, type RefObject } from 'react'
import {
  filterCommands,
  getSkillSlashCommands,
  isAppCommand,
  loadSkillSlashCommands,
} from '@/lib/slashCommands'

/**
 * Phase F + R33/R34: slash autocompletion for the composer — app commands and
 * skill triggers, the grouped menu data, the keyboard ring state and the
 * Enter/Tab confirm logic. The menu UI is chat/ComposerSlashMenu.
 * Extracted from ChatInput.tsx.
 */
export function useComposerSlash({
  message,
  setMessage,
  textareaRef,
  handleSend,
}: {
  message: string
  setMessage: (value: string) => void
  textareaRef: RefObject<HTMLTextAreaElement | null>
  handleSend: () => void
}) {
  // Phase F: slash autocompletion — suggestions only when the input starts with `/`
  // R34: skill triggers (/pdf, /factory …) extend the slash menu — loaded once
  // from GET /api/skills; a tick re-runs the memo when they arrive.
  const [skillCmds, setSkillCmds] = useState(() => getSkillSlashCommands())
  useEffect(() => {
    let live = true
    void loadSkillSlashCommands().then(() => {
      if (live) setSkillCmds(getSkillSlashCommands())
    })
    return () => {
      live = false
    }
  }, [])

  const slashSuggestions = useMemo(() => {
    const lead = message.trimStart()
    if (!lead.startsWith('/')) return []
    // I6 P1-3: the menu only leads while the command token itself is still being
    // typed. From the first space onward (argument phase) the choice is made —
    // otherwise Enter swallows half the input, because confirmSlash replaces
    // the field with the bare command line.
    const head = lead.replace(/^\/+/, '')
    if (/\s/.test(head)) return []
    return filterCommands(message, skillCmds)
  }, [message, skillCmds])

  // Group the menu: static app commands first, skill triggers in a second
  // section — with 60+ entries the groups keep the list scannable.
  // D3: the split asks the app what it ships, never the loaded skill list. A
  // skill that reuses a built-in trigger could otherwise re-file the built-in
  // row (walkthrough: /help under SKILLS).
  const slashAppHits = useMemo(
    () => slashSuggestions.filter((c) => isAppCommand(c.cmd)),
    [slashSuggestions],
  )
  const slashSkillHits = useMemo(
    () => slashSuggestions.filter((c) => !isAppCommand(c.cmd)),
    [slashSuggestions],
  )
  // Navigation order == visual order (Commands group above Skills group).
  const slashFlat = useMemo(
    () => [...slashAppHits, ...slashSkillHits],
    [slashAppHits, slashSkillHits],
  )
  // R33 keyboard-only menu control: highlighted row + Escape-dismissal.
  // Any text change re-opens the menu and resets the highlight (combobox norm).
  const [slashIndex, setSlashIndex] = useState(0)
  const [slashDismissed, setSlashDismissed] = useState(false)
  useEffect(() => {
    setSlashIndex(0)
    setSlashDismissed(false)
  }, [message])
  const slashOpen = slashSuggestions.length > 0 && !slashDismissed

  const applySuggestion = (cmd: string) => {
    // Keep the leading '/' — otherwise the next Enter is read as a normal
    // message instead of a slash command.
    setMessage('/' + cmd)
    textareaRef.current?.focus()
  }

  // Enter/Tab in the dropdown:
  //  - input = exact command → send directly (a second Enter would be annoying)
  //  - input = prefix        → take the first suggestion (the user adds the argument)
  const confirmSlash = (target?: { cmd: string }): boolean => {
    if (slashFlat.length === 0) return false
    // Compare on the command WITH the slash (c.cmd is stored without '/').
    const exact = slashFlat.some((c) => '/' + c.cmd === message.trim())
    if (exact) {
      handleSend()
      return true
    }
    applySuggestion((target ?? slashFlat[0])!.cmd)
    return true
  }

  return {
    slashAppHits,
    slashSkillHits,
    slashFlat,
    slashIndex,
    setSlashIndex,
    setSlashDismissed,
    slashOpen,
    applySuggestion,
    confirmSlash,
  }
}
