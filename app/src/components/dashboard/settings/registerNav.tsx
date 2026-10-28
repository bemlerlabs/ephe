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
import { ABOUT_KEYS, NAV_GROUPS, navIcon } from './model'
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

export interface RegisterNavProps {
  query: string
  tabHits: { key: TabKey }[]
  fieldHits: FieldHit[]
  rowHits: RowHit[]
  activeTab: TabKey
  t: SettingsModel['t']
  onJump: (tab: TabKey, secKey?: string) => void
  onSelect: (key: TabKey) => void
}

export function RegisterNav({
  query,
  tabHits,
  fieldHits,
  rowHits,
  activeTab,
  t,
  onJump,
  onSelect,
}: RegisterNavProps) {
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
                  onClick={() => onJump(tab, secKey)}
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
            <div
              key={group.groupKey}
              data-testid={`settings-nav-group-${group.groupKey.replace('settings.group', '').toLowerCase()}`}
              className="mb-2 max-md:flex max-md:items-center max-md:gap-1"
            >
              {/* Hidden at phone width, the chips ran as one undifferentiated strip
                  inside a long scroll — the heading is what makes a run readable. */}
              <p className={NAV_GROUP}>{t(group.groupKey)}</p>
              {group.keys.map((key) => {
                const Icon = navIcon(key)
                const selected = activeTab === key
                return (
                  <button
                    key={key}
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
                )
              })}
            </div>
          ))}
          <div
            data-testid="settings-nav-group-about"
            className="mb-2 max-md:flex max-md:items-center max-md:gap-1"
          >
            {ABOUT_KEYS.map((key) => {
              const Icon = navIcon(key)
              const selected = activeTab === key
              return (
                <button
                  key={key}
                  type="button"
                  data-testid={`settings-nav-${key}`}
                  onClick={() => onSelect(key)}
                  aria-current={selected ? 'true' : undefined}
                  className={`${NAV_ROW} max-md:w-auto max-md:shrink-0 max-md:snap-start max-md:whitespace-nowrap max-md:mb-0 border-y border-r border-dashed border-control ${
                    selected
                      ? 'border-l-hairline-strong text-ink'
                      : 'border-l-transparent text-ink-soft hover:text-ink'
                  }`}
                >
                  <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                  <span className="truncate">{t(`settings.${key}`)}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </>
  )
}
