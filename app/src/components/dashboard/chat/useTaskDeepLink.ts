/**
 * R4 (A3) — the way back out of the workbench.
 *
 * A card knows which task gave birth to it, and this link tells it:
 * `/chat?session=<id>&replay=1` restores the session and opens the replay tab,
 * where the turn sits with its steps and its files. The parameters are not left
 * in the URL — a reload must not redirect a second time.
 */
import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useChatStore } from '@/store/chatStore'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

export function useTaskDeepLink() {
  const [params, setParams] = useSearchParams()
  const session = params.get('session')
  const replay = params.get('replay')
  useEffect(() => {
    if (!session && !replay) return
    if (session) {
      const store = useChatStore.getState()
      if (store.activeSessionId !== session) store.setActiveSession(session)
    }
    if (replay) {
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'trajectory' } }))
    }
    setParams({}, { replace: true })
  }, [session, replay, setParams])
}
