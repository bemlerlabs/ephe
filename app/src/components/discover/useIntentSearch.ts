/** The intent index behind the search box: a task word finds the entry.
 *
 *  The index answers with the ids its catalog carries (`web-search`), while a card
 *  carries the kind in front of it (`connector:registry:web-search`); the lookup
 *  joins the two so a hit lands on the card it names. */
import { useEffect, useMemo, useState } from 'react'
import { searchDiscover } from '@/lib/api'
import type { DiscoverItem } from './discoverModel'

export function useIntentSearch(items: DiscoverItem[], needle: string): string[] {
  const [ids, setIds] = useState<string[]>([])

  const lookup = useMemo(() => {
    const table = new Map<string, string>()
    for (const item of items) {
      table.set(item.id, item.id)
      table.set(item.name, item.id)
      const bare = item.id.replace(/^connector:/, '')
      table.set(bare, item.id)
      table.set(bare.replace(/^registry:/, ''), item.id)
    }
    return table
  }, [items])

  useEffect(() => {
    if (needle.length < 3) {
      setIds([])
      return
    }
    let live = true
    const timer = window.setTimeout(() => {
      searchDiscover(needle)
        .then((hits) => {
          if (!live) return
          setIds(hits.map((hit) => lookup.get(hit.id)).filter((id): id is string => Boolean(id)))
        })
        .catch(() => {
          if (live) setIds([])
        })
    }, 150)
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [needle, lookup])

  return ids
}
