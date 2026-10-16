import { useEffect, useState } from 'react'

/**
 * A reactive CSS media-query hook.
 *
 * Used for responsive behaviour that needs a JAVASCRIPT decision (e.g.
 * framer-motion animations): the sidebar is a permanent column on desktop (lg+)
 * and a drawer on mobile. A pure CSS approach (transform classes) collides with
 * framer-motion's inline styles.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false,
  )

  useEffect(() => {
    // Defensive: matchMedia can be missing in reduced environments (jsdom/SSR)
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(query)
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches)
    // initial sync (SSR-/re-hydration safety)
    setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}
