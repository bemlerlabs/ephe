/**
 * Ephe — the composer's model menu (P3 wave 2026-10-05, split out of ChatInput).
 *
 * Finding P3-4: the container had no maximum height and no overflow-y — with
 * 56 scanned models the menu grew past the window edge (measured: height
 * 1470 px, top −782 px, 30 rows unreachable, scrolling impossible), and there
 * was neither search nor keyboard marking.
 *
 * Finding P3-5: between chat models stood an unfilled catalog placeholder
 * (`https://${SNOWFLAKE_ACCOUNT}…`) and speech models (whisper-1, base).
 * Hence: sections by type, template rows disabled with a reason,
 * loopback/tailnet endpoints not as a raw URL.
 *
 * S2: the list itself is now the shared `ModelPickerPanel` — the same search, filters,
 * sorts, favorites and metadata rows the setup page and the engine settings mount. What
 * stays here is what belongs to this host: the chip's anchor and placement, its own
 * chat / other / not-configured taxonomy, the endpoint wording, and the `onPick`
 * contract (`kind`, model, endpoint) the engine switch already spoke.
 */
import { useCallback, useMemo, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { ComposerMenu, MenuOptionRow, MenuSectionLabel } from './ComposerMenu'
import {
  entryKey,
  groupModelEntries,
  isActiveEntry,
  isUnconfiguredEntry,
  type ModelChipEntry,
} from './composerModelEntries'
import { rowsFromEntries, type ModelRow } from '@/components/model/modelPickerTypes'
import { ModelPickerPanel } from '@/components/model/ModelPickerPanel'
import type { MenuPos } from './composerPopups'

export interface ComposerModelMenuProps {
  pos: MenuPos | null
  anchorRef: RefObject<HTMLElement | null>
  entries: ModelChipEntry[]
  activeP: string
  model: string
  needsSetup: boolean
  onClose: () => void
  onPick: (id: string, model?: string, endpoint?: string) => void
  onSetup: () => void
}

export default function ComposerModelMenu({
  pos,
  anchorRef,
  entries,
  activeP,
  model,
  needsSetup,
  onClose,
  onPick,
  onSetup,
}: ComposerModelMenuProps) {
  const { t } = useTranslation()
  const labelChat = t('chat.modelGroupChat', { defaultValue: 'Chat models' })
  const labelOther = t('chat.modelGroupOther', { defaultValue: 'Other types (speech, image)' })
  const labelUnconfigured = t('chat.modelGroupUnconfigured', {
    defaultValue: 'No endpoint — not configurable',
  })

  /** Endpoint display: raw loopback/tailnet URLs do not belong in the list. */
  const hintOf = useCallback(
    (entry: ModelChipEntry): string => {
      if (isUnconfiguredEntry(entry))
        return t('chat.modelUnconfiguredHint', { defaultValue: 'not configured' })
      if (entry.endpointKind === 'loopback')
        return t('chat.modelEndpointLocal', { defaultValue: 'local' })
      if (entry.endpointKind === 'private')
        return t('chat.modelEndpointPrivate', { defaultValue: 'private network' })
      return entry.endpoint ?? ''
      // The wording is the translator's; the entry is the argument.
    },
    [t],
  )

  const groups = useMemo(() => groupModelEntries(entries), [entries])
  const { rows, byKey } = useMemo(() => {
    const chat = rowsFromEntries(groups.chat, labelChat, hintOf)
    const other = rowsFromEntries(groups.other, labelOther, hintOf)
    const unconfigured = rowsFromEntries(groups.unconfigured, labelUnconfigured, hintOf)
    const all = [...chat, ...other, ...unconfigured]
    const ordered = [...groups.chat, ...groups.other, ...groups.unconfigured]
    return {
      rows: all,
      byKey: new Map(all.map((row, i) => [row.key, ordered[i] as ModelChipEntry])),
    }
    // hintOf is a pure read of `t` and the entry; the four labels are its deps.
  }, [groups, labelChat, labelOther, labelUnconfigured, hintOf])

  const activeRow = useMemo(() => {
    for (const row of rows) {
      const entry = byKey.get(row.key)
      if (entry && isActiveEntry(entry, activeP, model)) return row
    }
    return undefined
  }, [rows, byKey, activeP, model])

  const choose = (row: ModelRow) => {
    const entry = byKey.get(row.key)
    if (!entry) return
    anchorRef.current?.focus()
    onPick(entry.kind ?? entryKey(entry), entry.model, entry.endpoint)
  }

  const sectionId = (section: { id: string; group?: string; labelKey: string }): string => {
    if (section.group === labelChat) return 'model-group-chat'
    if (section.group === labelOther) return 'model-group-other'
    if (section.group === labelUnconfigured) return 'model-group-unconfigured'
    if (section.id === 'favorites') return 'model-group-favorites'
    if (section.id === 'recent') return 'model-group-recent'
    return `model-${section.id}`
  }

  return (
    <ComposerMenu
      testId="model-chip-menu"
      pos={pos}
      anchorRef={anchorRef}
      onClose={onClose}
      role={null}
      widthClass="w-[min(30rem,calc(100vw-2rem))]"
      scroll="child"
    >
      {needsSetup && (
        <div role="group" data-testid="model-group-setup">
          <MenuSectionLabel>
            {t('chat.modelGroupSetup', { defaultValue: 'Set up the engine' })}
          </MenuSectionLabel>
          <MenuOptionRow
            id="model-opt-setup"
            testId="model-chip-option-setup"
            role="option"
            active={false}
            onSelect={onSetup}
          >
            {t('chat.setupEngineChip')}
          </MenuOptionRow>
        </div>
      )}
      <ModelPickerPanel
        rows={rows}
        value={activeRow?.id ?? model}
        selectedKey={activeRow?.key}
        onChoose={choose}
        onClose={(returnFocus) => {
          if (returnFocus) anchorRef.current?.focus()
          onClose()
        }}
        testId="model-chip"
        label={t('chat.modelSearchAria', { defaultValue: 'Search models' })}
        listLabel={t('chat.modelMenuAria', { defaultValue: 'Choose a model' })}
        placeholder={t('chat.modelSearchPlaceholder', {
          defaultValue: 'Type a model or endpoint…',
        })}
        count
        groupOf={(row) => row.group}
        groupOrder={[labelChat, labelOther, labelUnconfigured]}
        ids={{
          row: (row) => {
            const entry = byKey.get(row.key)
            return `model-chip-option-${entry ? entryKey(entry) : row.key}`
          },
          option: (row) => {
            const entry = byKey.get(row.key)
            return `model-opt-${entry ? entryKey(entry) : row.key}`
          },
          section: sectionId,
        }}
      />
    </ComposerMenu>
  )
}
