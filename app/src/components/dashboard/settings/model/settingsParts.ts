/**
 * The parts every settings area is built from — the nav's second level.
 *
 * Two kinds of part exist. A register block comes from the server schema and is
 * listed automatically (SECTION_TAB decides which tab it belongs to); a page part
 * is a block one of the section modules renders by hand. The second kind cannot
 * be discovered from the DOM, so it is named here and the anchor is the `testid`
 * that block already carries. registerNav.parts.test.ts reads the section sources
 * and refuses an entry whose anchor does not exist.
 *
 * The order of a tab's list is the order the page renders in. Where a register
 * block sits between two hand-built blocks, its reveal id is written into the
 * list instead of being appended.
 */
import type { DeepSection } from '@/types'
import type { TabKey } from '../types'
import { DEEP_PREFIX, sectionRevealId, sectionsOfTab } from './deepRegister'

export interface NavSub {
  /** The `data-testid` the block renders with — the scroll anchor. */
  id: string
  /** The same key the block's own heading uses, so the nav cannot say something
   *  the page does not. */
  labelKey: string
}

const part = (id: string, labelKey: string): NavSub => ({ id, labelKey })

const register = (secKey: string): NavSub =>
  part(sectionRevealId(secKey), `settings.deepSection.${secKey}`)

export const TAB_PARTS: Partial<Record<TabKey, NavSub[]>> = {
  engine: [
    part('engine-group-model', 'settings.chooseModel'),
    part('engine-group-access', 'settings.engineAccess'),
    part('engine-group-folders', 'settings.engineFolders'),
    part('engine-group-image', 'settings.imageTitle'),
    register('advanced'),
  ],
  appearance: [
    part('appearance-presets', 'settings.presetsTitle'),
    part('companion-studio', 'settings.companionStudioTitle'),
    register('appearance'),
    part('appearance-profile-group', 'settings.appearanceProfileTitle'),
  ],
  behaviour: [
    part('behaviour-group-workspace', 'settings.engineFolders'),
    part('custom-instructions-group', 'settings.customInstructionsTitle'),
    part('details-mode-group', 'settings.audienceTitle'),
    part('capability-matrix', 'settings.capabilityTitle'),
    part('behaviour-group-approval', 'settings.privacyGroupApproval'),
    register('chat'),
  ],
  generation: [
    part('generation-group-params', 'settings.generationGroup'),
    part('generation-group-reasoning', 'settings.genReasoningGroup'),
  ],
  voice: [
    part('voice-group-output', 'settings.audioGroupOutput'),
    part('voice-group-input', 'settings.audioGroupInput'),
  ],
  skills: [
    part('skills-group-install', 'settings.skillsGroupInstall'),
    part('skills-group-packs', 'settings.themedPacks'),
    part('skills-group-mine', 'settings.skillsGroupMine'),
    part('skills-group-builder', 'settings.skillBuilderTitle'),
  ],
  memory: [
    register('memory'),
    part('memory-group-store', 'settings.memoryGroupStore'),
    part('memory-group-entries', 'settings.memoryGroupEntries'),
    part('memory-group-danger', 'settings.memoryGroupDanger'),
  ],
  privacy: [
    part('privacy-group-device', 'settings.privacyGroupDevice'),
    part('session-store-group', 'settings.sessionStoreGroup'),
  ],
  tasks: [
    part('tasks-group-new', 'settings.tasksGroupNew'),
    part('tasks-group-list', 'settings.tasksGroupList'),
  ],
  mcp: [
    part('mcp-section-servers', 'settings.mcpServers'),
    part('mcp-section-catalog', 'settings.mcpCatalog'),
  ],
  plugins: [part('plugins-master', 'settings.pluginsGroupMaster'), register('plugins')],
  hooks: [
    part('hooks-file', 'settings.hooksGroupFile'),
    part('hooks-group-idle', 'settings.hooksGroupIdle'),
    part('hooks-group-recent', 'settings.hooksGroupRecent'),
    register('hooks'),
  ],
  'code-exec': [
    part('code-exec-runtime', 'settings.codeExecGroupRuntime'),
    part('code-exec-ceilings', 'settings.codeExecGroupCeilings'),
    part('code-exec-reach', 'settings.codeExecGroupReach'),
  ],
  network: [
    part('network-group-server', 'settings.networkGroupServer'),
    part('network-group-shares', 'settings.networkGroupShares'),
  ],
  shortcuts: [part('shortcuts-group-desktop', 'settings.shortcutsGroup.global'), register('shortcuts')],
  teams: [part('team-template-picker', 'settings.teamTemplate')],
  about: [part('settings-updates', 'settings.aboutUpdates')],
}

/** The blocks of one area, in page order. A register block that the server did
 *  not send is dropped — its rows are not on the page, so the nav must not offer
 *  a jump to nothing; a register block the page renders between two hand-built
 *  blocks is named in TAB_PARTS and stays where it is. */
export function subsOfTab(tab: TabKey, sections: DeepSection[] | null): NavSub[] {
  const deep = sectionsOfTab(sections, tab).map((sec) => register(sec.key))
  const sent = new Set(deep.map((one) => one.id))
  const parts = (TAB_PARTS[tab] ?? []).filter((one) => !one.id.startsWith(DEEP_PREFIX) || sent.has(one.id))
  const named = new Set(parts.map((one) => one.id))
  return [...parts, ...deep.filter((one) => !named.has(one.id))]
}
