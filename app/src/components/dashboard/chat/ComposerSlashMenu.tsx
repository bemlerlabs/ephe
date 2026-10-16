import { useTranslation } from 'react-i18next'
import { describeCommandDescription } from '@/lib/slashCommands'

/** One row in the slash-command autocomplete menu. R33: `active` marks the
 *  keyboard-highlighted option (ArrowUp/Down walks the flat list, Enter picks
 *  it) — aria-selected/aria-current make the highlight perceivable for AT. */
function SlashRow({
  c,
  active = false,
  onPick,
}: {
  c: { cmd: string; description: string; descKey?: string }
  active?: boolean
  onPick: (cmd: string) => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      id={`slash-opt-${c.cmd}`}
      role="option"
      aria-selected={active}
      aria-current={active ? 'true' : undefined}
      onClick={() => onPick(c.cmd)}
      className={`w-full text-left px-2.5 py-1.5 text-ui-xs text-foreground/70 hover:bg-brand/10 hover:text-foreground transition-colors flex items-center gap-2${active ? ' bg-brand/20 text-foreground' : ''}`}
    >
      <span className="font-mono text-brand/80 shrink-0">{`/${c.cmd}`}</span>
      {/* min-w-0 + flex-1 so the ellipsis can actually kick in inside the
          flex row — without them long descriptions hard-clip at the border. */}
      <span className="text-ink-faint truncate min-w-0 flex-1">
        {describeCommandDescription(c, t)}
      </span>
    </button>
  )
}

/**
 * Hand-rolled popup instead of a combobox library: the existing keyboard ring
 * (R33) and the testids stay untouched. Extracted from ChatInput.tsx — the
 * state lives in chat/useComposerSlash.
 */
export default function ComposerSlashMenu({
  appHits,
  skillHits,
  activeCmd,
  onPick,
}: {
  appHits: { cmd: string; description: string; descKey?: string }[]
  skillHits: { cmd: string; description: string; descKey?: string }[]
  activeCmd?: string
  onPick: (cmd: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div
      id="slash-menu"
      className="mb-2 rounded-lg border border-hairline bg-surface overflow-hidden"
      data-testid="slash-menu"
    >
      {/* Skill triggers push the list to 60+ rows: cap the height and
          scroll inside the menu instead of growing past the viewport. */}
      <div
        className="max-h-[240px] overflow-y-auto overscroll-contain"
        data-testid="slash-menu-scroll"
        role="listbox"
        aria-label={t('chat.commandsTitle')}
      >
        {appHits.length > 0 && (
          <>
            <p
              data-testid="slash-group-commands"
              className="px-2.5 pt-1.5 text-ui-xs uppercase tracking-wide text-ink-faint"
            >
              {t('chat.commandsTitle')}
            </p>
            {appHits.map((c) => (
              <SlashRow key={c.cmd} c={c} active={activeCmd === c.cmd} onPick={onPick} />
            ))}
          </>
        )}
        {skillHits.length > 0 && (
          <>
            <p
              data-testid="slash-group-skills"
              className="px-2.5 pt-1.5 text-ui-xs uppercase tracking-wide text-ink-faint"
            >
              {t('chat.skillsTitle')}
            </p>
            {skillHits.map((c) => (
              <SlashRow key={c.cmd} c={c} active={activeCmd === c.cmd} onPick={onPick} />
            ))}
          </>
        )}
      </div>
    </div>
  )
}
