import { useEffect, useMemo, useState } from 'react'
import { heroOf, type DiscoverItem, type DiscoverQuery } from './discoverModel'

/** The quiet default view: no tab, no phrase, no facet. */
export function browsingPicks(query: DiscoverQuery): boolean {
  return Boolean(query.query || query.category || query.origin || query.tab !== 'all')
}

/** Motion is a preference, not a default: the hero stays still when it is off. */
export function prefersStill(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/**
 * The featured shelf's turn: the hero steps through the first three picks every
 * eight seconds while the page sits on its default view. Hover or focus holds
 * it; a reduced-motion preference keeps it still.
 */
export function useFeaturedRotation(
  items: DiscoverItem[],
  query: DiscoverQuery,
  shown: DiscoverItem[],
) {
  const featured = useMemo(
    () =>
      [...items]
        .filter((item) => item.featured !== undefined)
        .sort((a, b) => Number(a.featured) - Number(b.featured)),
    [items],
  )
  const [pick, setPick] = useState(0)
  const [paused, setPaused] = useState(false)
  const still = prefersStill()
  useEffect(() => {
    if (still || paused || browsingPicks(query) || featured.length < 2) return undefined
    const timer = window.setInterval(
      () => setPick((current) => (current + 1) % Math.min(3, featured.length)),
      8000,
    )
    return () => window.clearInterval(timer)
  }, [still, paused, query, featured.length])
  const hero = useMemo(
    () =>
      browsingPicks(query) || !featured.length
        ? heroOf(shown)
        : (featured[pick % Math.min(3, featured.length)] ?? heroOf(shown)),
    [query, featured, pick, shown],
  )
  return { featured, hero, pick, setPick, setPaused }
}
