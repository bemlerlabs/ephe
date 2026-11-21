/**
 * The public hop's notice, loaded when the pairing group needs it. The wrapper is a
 * component so the settings module keeps exporting only what it always did and the
 * dev-time fast-refresh rule stays quiet.
 */
import { Suspense, lazy } from 'react'

import type { PublicTunnelNoticeProps } from './PublicTunnelNotice'

const Notice = lazy(() =>
  import('./PublicTunnelNotice').then((m) => ({ default: m.PublicTunnelNotice })),
)

export function PublicTunnelNoticeLazy(props: PublicTunnelNoticeProps) {
  return (
    <Suspense fallback={null}>
      <Notice {...props} />
    </Suspense>
  )
}
