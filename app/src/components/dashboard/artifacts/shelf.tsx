/**
 * Ephe — the shelf: artifacts by the kind their own tool set (R4/A2).
 *
 * Grouping is by `kind`, not by MIME sniffing — `kind` comes from the FILE marker
 * of the producing tool and is therefore the statement about what the file *is*,
 * not what the extension claims. The same row element as in the pop-up: one card,
 * two ways in.
 */
import { useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import type { ArtifactEntry } from '@/lib/api'
import ArtifactLibraryRow, { originOf } from './libraryRow'

/** A group shows eight cards; everything past that is a click, not a scroll run. */
const GROUP_LIMIT = 8

/**
 * Kind names come from the locale file. They stood here as German constants in an
 * English surface — "BILD 4" above an interface that says "Shelf".
 */
export function kindLabel(kind: string, t: (k: string) => string): string {
  const key = (kind || 'file').toLowerCase()
  const label = t(`artifacts.kind.${key}`)
  return label === `artifacts.kind.${key}` ? key.toUpperCase() : label
}

/**
 * The origins one name carries twice inside a group. That is the collision the
 * provenance tag cannot break — R6: a task that writes the same file twice in one
 * minute stamps both cards with its own id — so those rows have to fall back to the
 * birth the index stores, second by second. A card with no turn and no session is
 * never listed: an absent origin proves nothing and invents nothing.
 */
function tiedOrigins(rows: ArtifactEntry[]): Map<string, Set<string>> {
  const byName = new Map<string, Map<string, number>>()
  for (const a of rows) {
    const origin = originOf(a)
    if (!origin) continue
    const counts = byName.get(a.name) ?? new Map<string, number>()
    counts.set(origin, (counts.get(origin) ?? 0) + 1)
    byName.set(a.name, counts)
  }
  const tied = new Map<string, Set<string>>()
  for (const [name, counts] of byName) {
    const repeated = new Set([...counts].filter(([, n]) => n > 1).map(([o]) => o))
    if (repeated.size > 0) tied.set(name, repeated)
  }
  return tied
}

export default function ArtifactShelf({
  items,
  selectedId,
  onSelect,
  onChanged,
  leerText,
}: {
  items: ArtifactEntry[]
  selectedId: string | null
  onSelect: (id: string) => void
  onChanged: () => void
  /** What the list says when it is empty. The surface knows the reason — the
   *  shelf is empty when nothing was produced, the archive already when nothing
   *  has been adopted. */
  leerText?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState<Set<string>>(new Set())
  const reduceMotion = useReducedMotion()
  const groups: [string, ArtifactEntry[]][] = []
  const byKind = new Map<string, ArtifactEntry[]>()
  for (const a of items) {
    const key = (a.kind || 'file').toLowerCase()
    if (!byKind.has(key)) {
      byKind.set(key, [])
      groups.push([key, byKind.get(key)!])
    }
    byKind.get(key)!.push(a)
  }
  groups.sort((x, y) => y[1].length - x[1].length || x[0].localeCompare(y[0]))
  // The collision arises *inside* the group: five `file-summary.pdf` under each
  // other are not separated by the kind, which only separates across groups. So
  // counting happens per group, and only the repeat carries a mark.
  const doppelteNamen = new Map<string, Set<string>>()
  // One step finer: among those repeats, the cards that also share their origin —
  // the pair the tag cannot split, which then reads the birth down to the second.
  const tiedByGroup = new Map<string, Map<string, Set<string>>>()
  for (const [kind, rows] of groups) {
    const gesehen = new Set<string>()
    const doppelt = new Set<string>()
    for (const a of rows) {
      if (gesehen.has(a.name)) doppelt.add(a.name)
      else gesehen.add(a.name)
    }
    doppelteNamen.set(kind, doppelt)
    tiedByGroup.set(kind, tiedOrigins(rows))
  }

  if (items.length === 0) {
    return (
      <p
        className="py-10 text-center text-ui-xs text-ink-faint"
        data-testid="artifacts-shelf-empty"
      >
        {leerText ?? t('artifacts.page.empty')}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {groups.map(([kind, rows], i) => (
        <m.section
          key={kind}
          aria-label={kindLabel(kind, t)}
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.18,
            delay: reduceMotion ? 0 : Math.min(i, 4) * 0.03,
            ease: 'easeOut',
          }}
        >
          <h2
            className="px-2 pb-1 text-ui-2xs font-semibold uppercase tracking-wide text-ink-faint"
            data-testid={`shelf-group-${kind}`}
          >
            {kindLabel(kind, t)} <span className="text-ink-faint/70">{rows.length}</span>
          </h2>
          <div className="space-y-0.5">
            {(open.has(kind) ? rows : rows.slice(0, GROUP_LIMIT)).map((a) => (
              <ArtifactLibraryRow
                key={a.id}
                art={a}
                selected={a.id === selectedId}
                onSelect={() => onSelect(a.id)}
                onFavorite={onChanged}
                ambiguous={doppelteNamen.get(kind)?.has(a.name) ?? false}
                preciseStamp={tiedByGroup.get(kind)?.get(a.name)?.has(originOf(a)) ?? false}
              />
            ))}
            {rows.length > GROUP_LIMIT && (
              <button
                onClick={() =>
                  setOpen((prev) => {
                    const next = new Set(prev)
                    if (next.has(kind)) next.delete(kind)
                    else next.add(kind)
                    return next
                  })
                }
                className="min-h-7 max-lg:min-h-11 px-2 py-1 text-ui-2xs font-medium text-ink-soft hover:text-foreground/80"
                data-testid={`shelf-more-${kind}`}
              >
                {open.has(kind)
                  ? t('artifacts.page.showLess')
                  : t('artifacts.page.showMore', { n: rows.length - GROUP_LIMIT })}
              </button>
            )}
          </div>
        </m.section>
      ))}
    </div>
  )
}
