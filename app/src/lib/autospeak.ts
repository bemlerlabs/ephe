/**
 * R18: auto read-aloud per session (the YOLO toggle pattern in the StatusBar).
 * The session key overrides the global default ('ephe.autospeak' from the
 * privacy tab); 'ephe:autospeak-changed' keeps every consumer in sync.
 */
const GLOBAL_KEY = 'ephe.autospeak'
const sessionKey = (sessionId: string) => `ephe.autospeak.session.${sessionId}`
export const AUTOSPEAK_CHANGED_EVENT = 'ephe:autospeak-changed'

export function isAutospeakActive(sessionId?: string | null): boolean {
  try {
    if (sessionId) {
      const v = localStorage.getItem(sessionKey(sessionId))
      if (v !== null) return v === '1'
    }
    return localStorage.getItem(GLOBAL_KEY) === '1'
  } catch {
    return false
  }
}

export function setAutospeak(sessionId: string | null | undefined, value: boolean): void {
  try {
    localStorage.setItem(sessionId ? sessionKey(sessionId) : GLOBAL_KEY, value ? '1' : '0')
  } catch {
    /* Storage full/private — the toggle stays unpersisted */
  }
  window.dispatchEvent(new CustomEvent(AUTOSPEAK_CHANGED_EVENT))
}
