'use client'

/**
 * The register's navigation column — the search hits and the three nav groups.
 *
 * Its own module: index.tsx stood at 453 lines against the 400-line wall in
 * architecture-policy.yaml, and this block leaves without touching the page's
 * state, its focus trap or its scroll column. The props below are what the
 * column reads, nothing more.
 *
 * Direction: a nav row carries a label at the UI step with a 12 px glyph, and the
 * row you are in takes a 2 px hairline on its left edge plus ink. A nav row says
 * where you are, so the one accent stays for what is running now, and no fill or
 * radius is spent to say it. A group name is the 11 px mono label the direction
 * draws above its rows.
 */
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { NAV_GROUPS, navIcon } from './model'
import { sectionRevealId } from './model/deepRegister'
import { subsOfTab } from './model/settingsParts'
import type { DeepSection } from '@/types'
import type { SettingsModel } from './model/buildModel'
import type { FieldHit, RowHit } from './model/settingsSearch'
import type { TabKey } from './types'

/** The nav row: the left border is always two pixels wide, so the 2 px rule of
 *  the selected row moves no text when the selection changes. */
const NAV_ROW =
  'focus-ring w-full flex items-center gap-2.5 border-l-2 px-3 py-1.5 text-scale-ui transition-colors pointer-coarse:min-h-11'

/** The group name above a run of nav rows: the 11 px mono label of the direction. */
const NAV_GROUP =
  'font-mono text-scale-data uppercase tracking-wider text-ink-faint px-3 pt-2 pb-1 max-md:px-1 max-md:py-0 max-md:self-center max-md:shrink-0'

const HIT_ROW =
  'focus-ring w-full flex items-center gap-2.5 px-3 py-1.5 text-scale-ui transition-colors'

/** Which groups the reader folded away, remembered across openings. */
const FOLDED_KEY = 'ephe.settings.foldedGroups'

function readFolded(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(FOLDED_KEY) || '[]')
    return Array.isArray(raw) ? raw.filter((one) => typeof one === 'string') : []
  } catch {
    return []
  }
}

export interface RegisterNavProps {
  query: string
  tabHits: { key: TabKey }[]
  fieldHits: FieldHit[]
  rowHits: RowHit[]
  activeTab: TabKey
  /** The schema's sections; the active tab lists its own beneath the row. */
  sections?: DeepSection[] | null
  t: SettingsModel['t']
  onJump: (tab: TabKey, revealId?: string) => void
  onSelect: (key: TabKey) => void
}

export function RegisterNav({
  query,
  tabHits,
  fieldHits,
  rowHits,
  activeTab,
  sections = null,
  t,
  onJump,
  onSelect,
}: RegisterNavProps) {
  const [folded, setFolded] = useState<string[]>(readFolded)

  const toggleGroup = (groupKey: string) => {
    setFolded((current) => {
      const next = current.includes(groupKey)
        ? current.filter((one) => one !== groupKey)
        : [...current, groupKey]
      try {
        localStorage.setItem(FOLDED_KEY, JSON.stringify(next))
      } catch {
        // A browser that refuses storage still folds for this visit.
      }
      return next
    })
  }

  return (
    <>
      {/* I3-V5: search in the navigation — it finds areas and the single
          setting, and jumps there. That made the expert box redundant. */}
      {query ? (
        <div className="space-y-2 max-md:w-full" data-testid="settings-search-results">
          {tabHits.length === 0 && fieldHits.length === 0 && rowHits.length === 0 && (
            <p
              data-testid="settings-search-empty"
              className="px-3 py-2 text-scale-ui text-ink-faint"
            >
              {t('settings.settingsSearchEmpty')}
            </p>
          )}
          {tabHits.length > 0 && (
            <>
              <p className={NAV_GROUP}>
                {t('settings.settingsSearchTabs')}
                <span data-testid="settings-search-tabs-count" className="ml-1 tabular-nums">
                  {tabHits.length}
                </span>
              </p>
              {tabHits.map((hit) => {
                const Icon = navIcon(hit.key)
                return (
                  <button
                    key={`tab-${hit.key}`}
                    type="button"
                    data-testid={`settings-search-tab-${hit.key}`}
                    onClick={() => onJump(hit.key)}
                    className={`${HIT_ROW} border-l-2 border-transparent text-ink-soft hover:text-ink`}
                  >
                    <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                    <span className="truncate">{t(`settings.${hit.key}`)}</span>
                  </button>
                )
              })}
            </>
          )}
          {fieldHits.length + rowHits.length > 0 && (
            <>
              <p className={NAV_GROUP}>
                {t('settings.settingsSearchFields')}
                <span data-testid="settings-search-fields-count" className="ml-1 tabular-nums">
                  {fieldHits.length + rowHits.length}
                </span>
              </p>
              {fieldHits.map(({ secKey, label, tab }) => (
                <button
                  key={`field-${secKey}-${label}`}
                  type="button"
                  data-testid={`settings-search-field-${secKey}-${label}`}
                  onClick={() => onJump(tab, sectionRevealId(secKey))}
                  className={`${HIT_ROW} border-l-2 border-transparent text-ink-soft hover:text-ink`}
                  title={label}
                >
                  <span className="shrink-0 text-scale-data text-ink-faint">
                    {t(`settings.deepSection.${secKey}`, { defaultValue: secKey })}
                  </span>
                  <span className="truncate">{label}</span>
                </button>
              ))}
              {rowHits.map(({ tab, label }) => (
                <button
                  key={`row-${tab}-${label}`}
                  type="button"
                  data-testid={`settings-search-row-${tab}-${label}`}
                  onClick={() => onJump(tab)}
                  className={`${HIT_ROW} border-l-2 border-transparent text-ink-soft hover:text-ink`}
                  title={label}
                >
                  <span className="shrink-0 text-scale-data text-ink-faint">
                    {t(`settings.${tab}`)}
                  </span>
                  <span className="truncate">{label}</span>
                </button>
              ))}
            </>
          )}
        </div>
      ) : (
        <></>
      )}
      {!query && (
        <div className="max-md:flex max-md:w-full max-md:gap-1 max-md:overflow-x-auto max-md:snap-x max-md:snap-mandatory max-md:[scrollbar-width:none] max-md:[&::-webkit-scrollbar]:hidden max-md:[mask-image:linear-gradient(to_right,transparent_0,black_12px,black_calc(100%-28px),transparent_100%)]">
          {NAV_GROUPS.map((group) => (
            <div key={group.groupKey} className="mb-2 max-md:contents">
              {/* The heading names the run and stays inert; the chevron beside it folds
                  the rows, and the fold is remembered. The parity walk clicks every
                  `settings-nav-*` element, so a heading that folded its own rows would
                  hide the very rows it is walked for. On a phone the group is `contents`:
                  its heading and rows sit in the one horizontal strip. */}
              <p
                data-testid={`settings-group-head-${group.groupKey.replace('settings.group', '').toLowerCase()}`}
                className={NAV_GROUP}
              >
                {t(group.groupKey)}
                <button
                  type="button"
                  data-testid={`settings-fold-${group.groupKey.replace('settings.group', '').toLowerCase()}`}
                  aria-expanded={!folded.includes(group.groupKey)}
                  aria-label={t('settings.groupFold')}
                  onClick={() => toggleGroup(group.groupKey)}
                  className="focus-ring ml-1 hidden align-middle md:inline-flex"
                >
                  {folded.includes(group.groupKey) ? (
                    <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
                  ) : (
                    <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
                  )}
                </button>
              </p>
              <div
                data-testid={`settings-group-rows-${group.groupKey.replace('settings.group', '').toLowerCase()}`}
                className={folded.includes(group.groupKey) ? 'hidden md:block' : 'contents'}
              >
                {group.keys.map((key) => {
                  const Icon = navIcon(key)
                  const selected = activeTab === key
                  // The second level opens under the row you are in: the register
                  // blocks come from the schema, the page blocks from TAB_PARTS, and
                  // a click lands the column on that block.
                  const subs = selected ? subsOfTab(key, sections) : []
                  return (
                    <div key={key} className="max-md:contents">
                      <button
                        type="button"
                        data-testid={`settings-nav-${key}`}
                        onClick={() => onSelect(key)}
                        aria-current={selected ? 'true' : undefined}
                        className={`${NAV_ROW} max-md:w-auto max-md:shrink-0 max-md:snap-start max-md:whitespace-nowrap max-md:mb-0 ${
                          selected
                            ? 'border-l-hairline-strong text-ink'
                            : 'border-l-transparent text-ink-soft hover:text-ink'
                        }`}
                      >
                        <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                        <span className="truncate">{t(`settings.${key}`)}</span>
                      </button>
                      {subs.length > 0 && (
                        <div
                          data-testid={`settings-nav-sections-${key}`}
                          className="hidden border-l border-hairline/60 py-0.5 pl-6 md:block"
                        >
                          {subs.map((sub) => (
                            <button
                              key={sub.id}
                              type="button"
                              data-testid={`settings-nav-part-${key}-${sub.id}`}
                              onClick={() => onJump(key, sub.id)}
                              className="focus-ring block w-full px-2 py-1 text-left text-scale-data text-ink-faint transition-colors hover:text-ink"
                            >
                              {t(sub.labelKey)}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
