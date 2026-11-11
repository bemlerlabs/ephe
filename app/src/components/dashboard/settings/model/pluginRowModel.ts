/**
 * The facts a plugin row states, separated from the row that paints them.
 *
 * Three questions are answered here, and each has exactly one answer:
 *
 *   - Is this bundle on, off, or broken? `enabled` is the switch; a catalog entry
 *     whose own manifest could not be read has no rail, no tool count and no
 *     surface, and calling that "off" would hide the reason the switch does nothing.
 *   - What can it do? Tools, the surface it declares, and the slash commands the
 *     command route reports for it. A declarative bundle's zero tools are a fact and
 *     are said in words, not drawn as a number that reads like a count of nothing.
 *   - Where does it come from, and may it be removed? A bundled plugin ships with the
 *     app; a plugin installed on this device is the one the remove path may touch.
 *
 * Nothing here calls a route or reads a store: the row and the hook stay the only
 * places that do, and the copy is passed in because the locale is the caller's.
 */
import type { MarketInstalledRow, PluginCommandInfo, PluginEntry, PluginView } from '@/lib/api'
import { ApiError } from '@/lib/api'

export type PluginStatus = 'active' | 'inactive' | 'faulty'

export type Translator = (key: string, options?: Record<string, unknown>) => string

/**
 * A bundle is broken when the catalog says it has a manifest and the scan could not
 * read one. `manifest === false` is the other thing entirely: a catalog entry with no
 * directory behind it (or an installed row filled in from the marketplace), whose
 * missing rail says nothing about its health.
 */
export function pluginStatus(entry: PluginEntry): PluginStatus {
  if (entry.manifest === true && entry.rail === undefined) return 'faulty'
  return entry.enabled ? 'active' : 'inactive'
}

export function statusKey(status: PluginStatus): string {
  if (status === 'active') return 'settings.pluginStatusActive'
  if (status === 'inactive') return 'settings.pluginStatusInactive'
  return 'settings.pluginStatusFaulty'
}

/** How many tools this bundle contributes, or `null` when no manifest was read. */
export function toolCount(entry: PluginEntry): number | null {
  if (entry.rail === 'worker') return entry.contributed_tools ?? 0
  if (entry.rail === 'kernel') return entry.activated_tools ?? 0
  if (entry.rail === 'declarative') return 0
  return null
}

/** The first tool's own name, read off the module the manifest declared. */
export function toolExample(entry: PluginEntry): string {
  const module = (entry.module ?? '').trim()
  if (!module) return ''
  const afterColon = module.includes(':') ? module.slice(module.lastIndexOf(':') + 1) : ''
  if (afterColon) return afterColon
  const file = module.split('/').pop() ?? module
  return file.replace(/\.(py|js|mjs|ts)$/, '')
}

export function surfaceTitle(entry: PluginEntry): string {
  return entry.surface?.title || entry.surface?.type || ''
}

/** Command names this plugin owns, in the order the route returned them. */
export function commandsFor(entry: PluginEntry, commands: PluginCommandInfo[] | null): string[] {
  return (commands ?? [])
    .filter((command) => command.plugin === entry.id)
    .map((command) => command.name)
}

export type PluginSource = 'builtin' | 'user'

export function pluginSource(entry: PluginEntry): PluginSource | null {
  if (entry.source === 'builtin' || entry.source === 'user') return entry.source
  return null
}

/** Only an install on this device can be taken off it again. */
export function canRemove(entry: PluginEntry): boolean {
  return pluginSource(entry) === 'user'
}

export function sourceKey(source: PluginSource): string {
  return source === 'user' ? 'settings.pluginSourceUser' : 'settings.pluginSourceBuiltin'
}

export function trustKey(entry: PluginEntry): string | null {
  if (entry.origin === 'external') return 'settings.pluginOriginExternal'
  if (entry.origin === 'first-party') return 'settings.pluginOriginFirstParty'
  return null
}

/**
 * An installed bundle with no catalog entry, as the marketplace's installed view
 * describes it. It has a manifest (the route scanned it) but this store view never
 * received its rail or surface, so `manifest: false` keeps the status rule honest:
 * nothing here may claim the manifest is broken.
 */
export function installedEntry(row: MarketInstalledRow): PluginEntry {
  return {
    id: row.name,
    name: row.name,
    description: row.description,
    tags: [],
    example_prompts: [],
    enabled: row.enabled,
    version: row.version || undefined,
    origin: row.origin === 'user' ? 'external' : 'first-party',
    source: row.origin === 'user' ? 'user' : 'builtin',
    permissions: row.permissions?.tool_families ?? [],
    components: row.components ?? [],
    manifest: false,
  }
}

/** The sentence a refused switch or removal puts in the row, never the raw envelope. */
export function pluginErrorText(reason: unknown, t: Translator, fallback: string): string {
  if (reason instanceof ApiError) {
    switch (reason.reasonCode) {
      case 'dependency_blocked':
        return t('settings.pluginErrorDependency', { name: reason.message })
      case 'dependents_enabled':
        return t('settings.pluginErrorDependents', { name: reason.message })
      case 'stale_state':
        return t('settings.pluginErrorStale')
      case 'not_cancellable':
        return t('settings.pluginErrorNotCancellable')
      case 'plugin_lifecycle_read_only':
        return t('settings.pluginErrorReadOnly')
      case 'plugin_enabled':
      case 'plugin_must_be_disabled':
        return t('settings.pluginRemoveEnabled')
      case 'not_installed':
      case 'plugin_unknown':
        return t('settings.pluginErrorUnknown')
      case 'signature_denied':
      case 'signature_invalid':
        return t('settings.pluginErrorSignature')
      default:
        break
    }
    if (reason.status === 0) return t('settings.pluginErrorNetwork')
    if (reason.status === 401 || reason.status === 403) return t('settings.pluginErrorAuth')
  }
  return reason instanceof Error && reason.message ? reason.message : fallback
}

/** Which of the two segment groups a view holds, without assuming both keys exist. */
export function pluginSegments(view: PluginView | null): {
  global: PluginEntry[]
  session: PluginEntry[]
} {
  if (!view) return { global: [], session: [] }
  if (view.global !== undefined || view.session !== undefined) {
    return { global: view.global ?? [], session: view.session ?? [] }
  }
  const pool = [...(view.public ?? []), ...(view.personal ?? [])]
  return {
    global: pool.filter((row) => row.scope !== 'session'),
    session: pool.filter((row) => row.scope === 'session'),
  }
}
