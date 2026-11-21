/**
 * The About tab's update block, loaded when the tab is opened. The wrapper is a
 * component so the settings module keeps exporting only what it always did and
 * the dev-time fast-refresh rule stays quiet.
 */
import { Suspense, lazy } from 'react'

const Section = lazy(() => import('./UpdateSection').then((m) => ({ default: m.UpdateSection })))

export function UpdateSectionLazy() {
  return (
    <Suspense fallback={null}>
      <Section />
    </Suspense>
  )
}
