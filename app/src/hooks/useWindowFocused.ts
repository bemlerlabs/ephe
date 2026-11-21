import { useEffect, useState } from 'react'

/**
 * P1 [F6]: window focus/visibility as one hook — unifying visibilitychange (tab in
 * the background), window blur/focus (another window on top) and a synchronous
 * initial value. The basis for "artifact ready → a toast instead of opening the
 * preview, as long as the user is not looking".
 */
export function useWindowFocused(): boolean {
  const [focused, setFocused] = useState(() => isWindowFocused())
  useEffect(() => {
    const update = () => setFocused(isWindowFocused())
    document.addEventListener('visibilitychange', update)
    window.addEventListener('focus', update)
    window.addEventListener('blur', update)
    return () => {
      document.removeEventListener('visibilitychange', update)
      window.removeEventListener('focus', update)
      window.removeEventListener('blur', update)
    }
  }, [])
  return focused
}

export function isWindowFocused(): boolean {
  if (typeof document === 'undefined') return true
  return document.visibilityState === 'visible' && document.hasFocus()
}
