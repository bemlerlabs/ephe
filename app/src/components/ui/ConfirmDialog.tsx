/**
 * Ephe — the sheet a destructive action asks through (finding #68), mounted once by the
 * app shell. `askConfirm` in `@/lib/confirmAction` holds the question; this renders it with
 * the verb on the button.
 */
import { useEffect, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from './Button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './Dialog'
import {
  answerConfirm,
  pendingConfirm,
  registerConfirmHost,
  subscribeConfirm,
} from '@/lib/confirmAction'

export function ConfirmHost() {
  const { t } = useTranslation()
  useEffect(() => registerConfirmHost(), [])
  const request = useSyncExternalStore(subscribeConfirm, pendingConfirm)

  return (
    <Dialog
      open={request !== null}
      onOpenChange={(open) => {
        if (!open) answerConfirm(false)
      }}
    >
      <DialogContent className="max-w-md" data-testid="confirm-dialog">
        <DialogHeader>
          <DialogTitle data-testid="confirm-title">{request?.title ?? ''}</DialogTitle>
        </DialogHeader>
        <div className="mt-5 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-testid="confirm-cancel"
            onClick={() => answerConfirm(false)}
            className="max-lg:min-h-11"
          >
            {request?.cancel ?? t('common.cancel')}
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            data-testid="confirm-action"
            onClick={() => answerConfirm(true)}
            className="max-lg:min-h-11"
          >
            {request?.action ?? ''}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
