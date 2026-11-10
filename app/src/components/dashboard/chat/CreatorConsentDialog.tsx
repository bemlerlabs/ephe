/**
 * Ephe — the sheet Creator Mode asks for its permissions through.
 *
 * `core/tools/creator_guard.py` (`80e3852f`) enforces `code`, `files` and
 * `network` one call at a time, and the ruling that governs entry is the
 * owner's: holding any one of the three is enough for a session to have Creator
 * mode at all, while each call still needs the permission it uses. This is the
 * only place that ruling reaches a person's eyes, so the rows are the guard's
 * own closed set (`CREATOR_PRIVILEGES`) and the enter control refuses the empty
 * set the ruling refuses.
 *
 * The read is deliberately not silent. A session that holds nothing and a
 * session the app could not ask are different answers, and rendering the first
 * when the second happened would show three unchecked rows as if the user had
 * declined them. So a failed read says so and leaves the write to the user.
 *
 * A grant is keyed to one session, never to the device — a second chat asks for
 * its own permissions, which is why this sheet takes `sessionId` and re-reads
 * every time it opens.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CREATOR_PRIVILEGES, getCreatorConsent, putCreatorConsent } from '@/lib/api'
import type { CreatorPrivilege } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/Dialog'

export interface CreatorConsentDialogProps {
  open: boolean
  /** The session the grant is written for. Consent is never device-wide. */
  sessionId: string
  /** Called with what was written, after the write answered. */
  onConfirm: (privileges: CreatorPrivilege[]) => void
  /** Called on every path that leaves the sheet without a grant. */
  onClosed: () => void
}

/** The chosen set in the guard's own order, so the stored value reads the same
 *  however the rows were clicked. */
function inGuardOrder(chosen: ReadonlySet<CreatorPrivilege>): CreatorPrivilege[] {
  return CREATOR_PRIVILEGES.filter((name) => chosen.has(name))
}

export default function CreatorConsentDialog({
  open,
  sessionId,
  onConfirm,
  onClosed,
}: CreatorConsentDialogProps) {
  const { t } = useTranslation()
  const [chosen, setChosen] = useState<ReadonlySet<CreatorPrivilege>>(new Set())
  const [readFailed, setReadFailed] = useState(false)
  const [writeFailed, setWriteFailed] = useState(false)
  const [writing, setWriting] = useState(false)

  useEffect(() => {
    if (!open) return
    let alive = true
    setReadFailed(false)
    setWriteFailed(false)
    setChosen(new Set())
    void getCreatorConsent(sessionId)
      .then((answer) => {
        if (!alive) return
        setChosen(new Set(answer.held))
      })
      .catch(() => {
        if (alive) setReadFailed(true)
      })
    return () => {
      alive = false
    }
  }, [open, sessionId])

  const toggle = useCallback((name: CreatorPrivilege) => {
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }, [])

  const enter = useCallback(async () => {
    const privileges = inGuardOrder(chosen)
    if (privileges.length === 0) return
    setWriting(true)
    setWriteFailed(false)
    try {
      await putCreatorConsent(sessionId, privileges)
      onConfirm(privileges)
    } catch {
      // The sheet stays, with the choice intact: closing it would say "you are in
      // Creator Mode" about a session the guard holds nothing for.
      setWriteFailed(true)
    } finally {
      setWriting(false)
    }
  }, [chosen, onConfirm, sessionId])

  if (!open) return null

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClosed()
      }}
    >
      <DialogContent className="max-w-md" data-testid="creator-consent-sheet">
        <DialogHeader>
          <DialogTitle data-testid="creator-consent-title">
            {t('chat.creatorConsent.title')}
          </DialogTitle>
        </DialogHeader>
        <p data-testid="creator-consent-intro" className="mt-1 text-ui-sm leading-relaxed">
          {t('chat.creatorConsent.intro')}
        </p>

        {readFailed && (
          <p
            role="alert"
            data-testid="creator-consent-read-failed"
            className="mt-3 rounded-md border border-status-warning/40 bg-surface px-3 py-2 text-ui-xs leading-relaxed text-status-warning"
          >
            {t('chat.creatorConsent.readFailed')}
          </p>
        )}

        {writeFailed && (
          <p
            role="alert"
            data-testid="creator-consent-write-failed"
            className="mt-3 rounded-md border border-status-warning/40 bg-surface px-3 py-2 text-ui-xs leading-relaxed text-status-warning"
          >
            {t('chat.creatorConsent.writeFailed')}
          </p>
        )}

        <fieldset className="mt-4 border-0 p-0">
          <legend className="sr-only">{t('chat.creatorConsent.title')}</legend>
          <div className="flex flex-col gap-2">
            {CREATOR_PRIVILEGES.map((name) => (
              <label
                key={name}
                data-testid={`creator-consent-${name}`}
                className="flex cursor-pointer items-start gap-3 rounded-lg border border-hairline bg-surface px-3 py-2.5"
              >
                <input
                  data-testid={`creator-consent-${name}-input`}
                  type="checkbox"
                  className="mt-0.5 shrink-0"
                  checked={chosen.has(name)}
                  onChange={() => toggle(name)}
                />
                <span className="flex min-w-0 flex-col">
                  <span className="text-ui-sm font-medium">
                    {t(`chat.creatorConsent.${name}.label`)}
                  </span>
                  <span className="text-ui-xs leading-relaxed text-ink-faint">
                    {t(`chat.creatorConsent.${name}.detail`)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <p
          data-testid="creator-consent-note"
          className="mt-3 text-ui-xs leading-relaxed text-ink-faint"
        >
          {t('chat.creatorConsent.note')}
        </p>

        <div className="mt-5 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid="creator-consent-cancel"
            onClick={onClosed}
            className="max-lg:min-h-11"
          >
            {t('chat.creatorConsent.cancel')}
          </Button>
          <Button
            type="button"
            size="sm"
            data-testid="creator-consent-enter"
            disabled={chosen.size === 0 || writing}
            onClick={() => void enter()}
            className="max-lg:min-h-11"
          >
            {t('chat.creatorConsent.enter')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
