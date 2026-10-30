/** The shelf as shelves, one per subject, each with the line that says what the
 *  subject is for. Entries are capped per shelf; "All n" turns the shelf into a
 *  filter, so a long subject never becomes an endless page. */
import { useTranslation } from 'react-i18next'
import { DiscoverCard } from './DiscoverCard'
import { Shelf } from './Shelf'
import type { DiscoverItem } from './discoverModel'

const PER_SECTION = 8

/** On this machine and used beats merely listed; measured downloads come next. */
function ranked(list: DiscoverItem[]): DiscoverItem[] {
  return [...list].sort(
    (a, b) =>
      Number(b.installed) - Number(a.installed) ||
      (b.calls ?? 0) - (a.calls ?? 0) ||
      (b.downloads ?? 0) - (a.downloads ?? 0) ||
      a.title.localeCompare(b.title),
  )
}

export function DiscoverSections({
  groups,
  busy,
  onAdd,
  onToggle,
  onDetail,
  onSeeAll,
}: {
  groups: [string, DiscoverItem[]][]
  busy: string
  onAdd: (item: DiscoverItem) => void
  onToggle: (item: DiscoverItem, next: boolean) => void
  onDetail: (item: DiscoverItem) => void
  onSeeAll: (key: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div data-testid="discover-sections" className="mt-12 space-y-11">
      {groups.map(([key, list]) => (
        <Shelf
          key={key}
          testId={`discover-section-${key}`}
          subject={key}
          title={t(`discover.category.${key}`, { defaultValue: key })}
          lede={t(`discover.section.${key}`, { defaultValue: '' })}
          action={
            list.length > PER_SECTION
              ? {
                  label: t('discover.seeAll', { count: list.length }),
                  testId: `discover-see-all-${key}`,
                  onClick: () => onSeeAll(key),
                }
              : undefined
          }
        >
          {ranked(list)
            .slice(0, PER_SECTION)
            .map((item) => (
              <DiscoverCard
                key={item.id}
                item={item}
                busy={busy === item.id}
                onAdd={onAdd}
                onToggle={onToggle}
                onDetail={onDetail}
              />
            ))}
        </Shelf>
      ))}
    </div>
  )
}
