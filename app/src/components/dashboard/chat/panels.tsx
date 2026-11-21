import { lazy, Suspense, useEffect, useState, type ComponentProps } from 'react'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { PanelOpenDetail } from '../agent/primitives'

// Both panes are their own chunks (W3-1) and default closed. They are mounted on
// the first request that opens them instead of at boot, so neither chunk is
// fetched for a reader who never opens a pane.
const AgentPanel = lazy(() => import('../AgentPanel'))
const SettingsPanel = lazy(() => import('../SettingsPanel'))

/** The agent pane is mounted on its first open request. Everything that opens it
 *  dispatches PREVIEW_OPEN_EVENT (header toggle, sidebar, palette, artifact
 *  chips, the replay deep link), so this gate listens until the pane's own
 *  listener exists and hands the pending request over: the click that caused the
 *  mount still opens the pane. */
export function DeferredAgentPanel({
  messages,
}: {
  messages: ComponentProps<typeof AgentPanel>['messages']
}) {
  const [request, setRequest] = useState<PanelOpenDetail | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (ready) return
    const onOpen = (event: Event) => {
      setRequest((event as CustomEvent<PanelOpenDetail | undefined>).detail ?? {})
    }
    window.addEventListener(PREVIEW_OPEN_EVENT, onOpen)
    return () => window.removeEventListener(PREVIEW_OPEN_EVENT, onOpen)
  }, [ready])
  if (!request) return null
  return (
    <Suspense fallback={null}>
      <AgentPanel messages={messages} boot={request} onReady={() => setReady(true)} />
    </Suspense>
  )
}

/** The settings register is one action away. It mounts on the first open and
 *  stays mounted afterwards, so the close transition and the last tab survive a
 *  dismissal exactly as they did while the panel was always in the tree. */
export function DeferredSettingsPanel(props: ComponentProps<typeof SettingsPanel>) {
  const [mounted, setMounted] = useState(props.isOpen)
  useEffect(() => {
    if (props.isOpen) setMounted(true)
  }, [props.isOpen])
  if (!mounted) return null
  return (
    <Suspense fallback={null}>
      <SettingsPanel {...props} />
    </Suspense>
  )
}
