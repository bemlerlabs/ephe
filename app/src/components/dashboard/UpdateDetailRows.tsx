/** The details disclosure of the update sheet: the package, the two versions,
 *  the size the transfer reported and the notes the feed carried. */
import { useTranslation } from 'react-i18next'
import { ChevronRight } from 'lucide-react'
import { DetailRow } from './UpdateNotes'
import { UpdateFacts } from './UpdateFacts'
import type { UpdateState } from '@/lib/updateCheckRun'
import { formatBytes } from '@/lib/updateDetails'

export function UpdateDetailRows({
  state,
  mainChannel,
}: {
  state: UpdateState
  mainChannel: boolean
}) {
  const { t } = useTranslation()
  const size = formatBytes(state.sizeBytes)
  const notReported = t('update.detailsUnknown')

  return (
          <details className="update-details mt-3" data-testid="update-details">
            <summary className="update-details-summary flex items-center gap-1.5 text-scale-ui text-ink-soft">
              <ChevronRight className="update-caret h-3.5 w-3.5" aria-hidden="true" />
              {t('update.details')}
            </summary>
            <div className="update-details-body mt-1 pl-6">
              <DetailRow
                label={t('update.detailsVersion')}
                value={
                  mainChannel
                    ? `${state.commit ?? '—'} → ${state.latest ?? 'main'}`
                    : `${state.current ?? '—'} → ${state.latest ?? '—'}`
                }
                mono
                testId="update-details-version"
              />
              <UpdateFacts
                commit={state.commit}
                channel={state.channel}
                commitLabel={t('update.detailsCommit')}
                channelLabel={t('update.detailsChannel')}
              />
              <DetailRow
                label={t('update.detailsSize')}
                value={size ?? notReported}
                mono={!!size}
                testId="update-details-size"
              />
              <DetailRow
                label={t('update.detailsPlatform')}
                value={state.platform ?? notReported}
                testId="update-details-platform"
              />
              <DetailRow
                label={t('update.detailsAsset')}
                value={state.asset ?? notReported}
                testId="update-details-asset"
              />
              {state.date && (
                <DetailRow
                  label={t('update.detailsDate')}
                  value={state.date.slice(0, 10)}
                  mono
                  testId="update-details-date"
                />
              )}
            </div>
          </details>
  )
}
