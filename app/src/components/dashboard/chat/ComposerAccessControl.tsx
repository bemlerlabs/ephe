/**
 * Ephe — the access side of the composer: the approval profile, shown as one
 * compact control with the active right in it (owner wish 2026-11-10).
 *
 * The four values are the ones the server accepts
 * (`core/security_config.py::VALID_APPROVAL_PROFILES`), not a new vocabulary:
 * the mode decides what a turn may run, this profile is the ceiling above that
 * decision (`settings.profileModeNote`). Picking here writes the profile for the
 * device through `/api/settings/security` and never touches a session's mode.
 *
 * Full access removes the asking, so an amber trigger with the alert shield marks it and the
 * menu says what stops being asked.
 */
import { useEffect, useMemo, useState, type RefObject } from 'react'
import { ChevronDown, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ACCESS_PROFILES, type AccessProfile } from './accessProfiles'
import { ComposerMenu, MenuOptionRow, useMenuFocus, useRovingSelection } from './ComposerMenu'
import type { MenuPos } from './composerPopups'

export interface ComposerAccessControlProps {
  profile: string
  open: boolean
  anchorRef: RefObject<HTMLButtonElement | null>
  menuPos: MenuPos | null
  onToggle: () => void
  onClose: () => void
  /** Writes the profile; a rejection leaves the shown value where it was. */
  onPick: (key: AccessProfile) => Promise<void>
}

export default function ComposerAccessControl({
  profile,
  open,
  anchorRef,
  menuPos,
  onToggle,
  onClose,
  onPick,
}: ComposerAccessControlProps) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const rows = useMemo(
    () => ACCESS_PROFILES.map((entry) => ({ ...entry, label: String(t(entry.labelKey)) })),
    [t],
  )
  const { index, move, setIndex } = useRovingSelection(rows.length, profile)
  // The ring starts on the active right; the check and the highlight agree.
  useEffect(() => {
    const at = ACCESS_PROFILES.findIndex((entry) => entry.key === profile)
    if (at >= 0) setIndex(at)
  }, [profile, setIndex])
  const { ref, release } = useMenuFocus(anchorRef)
  // A stored value outside the register (an old `autonomous` row) still shows a
  // word: the badge this control replaces named it through the same leaves.
  const short = String(t(`chat.perm.${profile}`, { defaultValue: profile }))
  const full = profile === 'full'
  const Icon = full ? ShieldAlert : ShieldCheck
  const activeRow = rows[Math.min(index, Math.max(0, rows.length - 1))]

  const choose = async (key: AccessProfile) => {
    if (key === profile) {
      release()
      onClose()
      return
    }
    setBusy(true)
    setFailed(false)
    try {
      await onPick(key)
      release()
      onClose()
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative inline-flex items-center shrink-0">
      <button
        type="button"
        ref={anchorRef}
        data-testid="composer-access-control"
        data-profile={profile}
        data-warning={full ? 'full' : undefined}
        aria-label={`${String(t('chat.permissionAria'))}: ${short}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-busy={busy || undefined}
        title={
          full
            ? `${short} — ${String(t('chat.accessFullWarning'))}`
            : String(t('chat.accessMenuNote'))
        }
        onClick={onToggle}
        className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-ui-xs transition-colors shrink-0 min-h-6 max-lg:min-h-11 max-lg:max-w-32 overflow-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ${
          full
            ? 'border-status-warning/40 bg-status-warning/10 text-status-warning'
            : 'border-hairline bg-surface text-ink-faint hover:text-foreground hover:border-brand/30'
        }`}
      >
        <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="truncate min-w-0">{short}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {open && menuPos && (
        <ComposerMenu
          testId="composer-access-menu"
          pos={menuPos}
          anchorRef={anchorRef}
          onClose={onClose}
          role={null}
          widthClass="w-72"
        >
          <div
            ref={ref}
            tabIndex={-1}
            data-testid="composer-access-list"
            role="menu"
            aria-label={t('chat.permissionAria')}
            aria-activedescendant={activeRow ? `access-opt-${activeRow.key}` : undefined}
            className="py-1.5 outline-none"
            onKeyDown={(ev) => {
              if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
                ev.preventDefault()
                move(ev.key === 'ArrowDown' ? 1 : -1)
              } else if (ev.key === 'Enter' || ev.key === 'Tab') {
                ev.preventDefault()
                if (activeRow) void choose(activeRow.key)
              } else if (ev.key === 'Escape') {
                ev.preventDefault()
                ev.stopPropagation()
                release()
                onClose()
              }
            }}
          >
            {rows.map((row) => {
              const ring = rows.findIndex((x) => x.key === row.key)
              return (
                <MenuOptionRow
                  key={row.key}
                  id={`access-opt-${row.key}`}
                  testId={`composer-access-${row.key}`}
                  role="menuitemradio"
                  active={ring === index}
                  selected={profile === row.key}
                  onSelect={() => void choose(row.key)}
                >
                  <span className="flex flex-col items-start">
                    <span className="text-ui-xs">{row.label}</span>
                  </span>
                </MenuOptionRow>
              )
            })}
          </div>
          {full && (
            <p
              data-testid="composer-access-full-warning"
              className="whitespace-normal border-t border-status-warning/30 px-3 py-2 text-ui-2xs leading-relaxed text-status-warning"
            >
              {t('chat.accessFullWarning')}
            </p>
          )}
          <p
            data-testid="composer-access-note"
            className="whitespace-normal border-t border-hairline px-3 py-2 text-ui-2xs leading-relaxed text-ink-faint"
          >
            {t('chat.accessMenuNote')}
          </p>
          {failed && (
            <p
              data-testid="composer-access-failed"
              role="status"
              className="whitespace-normal border-t border-hairline px-3 py-2 text-ui-2xs leading-relaxed text-status-danger"
            >
              {t('chat.accessSaveFailed')}
            </p>
          )}
        </ComposerMenu>
      )}
    </div>
  )
}
