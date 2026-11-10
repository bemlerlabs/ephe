/**
 * The hold and the hand on a watched browser session.
 *
 * Both posts stay on the app's own request path. The answer is a mode, never a frame.
 */
import { request } from '@/lib/api/http'

export type HoldAction = 'pause' | 'resume' | 'stop' | 'takeover' | 'handback'

export interface HoldResult {
  mode: string
  evidence?: string
}

export async function postBrowserHold(session: string, action: HoldAction): Promise<HoldResult> {
  return request<HoldResult>(`/api/browser/watch/${encodeURIComponent(session)}/hold`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
}

export async function postBrowserAct(
  session: string,
  body:
    | { kind: 'click'; x: number; y: number }
    | { kind: 'type'; text: string }
    | { kind: 'press'; key: string },
): Promise<{ acted: string }> {
  return request<{ acted: string }>(`/api/browser/watch/${encodeURIComponent(session)}/act`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
