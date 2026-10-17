/**
 * The React side of the one dispatcher: a surface hands in the rows it answers
 * for, keyed by table id, and this hook registers them into the single window
 * listener. A changed callback with the same ids does not re-register — the
 * handler reads through a ref, so a re-render cannot drop a key.
 */
import { useEffect, useRef } from 'react'
import {
  installShortcutListener,
  registerShortcut,
  type ShortcutHandler,
} from '@/lib/shortcutDispatch'
import type { ShortcutId } from '@/lib/shortcuts'

export type ShortcutMap = Partial<Record<ShortcutId, ShortcutHandler>>

export function useShortcutDispatch(map: ShortcutMap): void {
  const latest = useRef(map)
  latest.current = map
  const ids = Object.keys(map).sort().join(' ')

  useEffect(() => {
    const attached = ids
      .split(' ')
      .filter(Boolean)
      .map((id) =>
        registerShortcut(id as ShortcutId, (def, event) =>
          latest.current[id as ShortcutId]?.(def, event),
        ),
      )
    return () => attached.forEach((off) => off())
  }, [ids])

  useEffect(() => installShortcutListener(), [])
}
