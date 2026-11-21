'use client'

import type { SettingsPanelProps } from '../types'
import { useSettingsState } from './useSettingsState'
import { useSettingsCore } from './useSettingsCore'
import { useSettingsFeatures } from './useSettingsFeatures'
import { useSettingsLists } from './useSettingsLists'
import { useSettingsSave } from './useSettingsSave'
import { useInstantAppearance } from './useInstantAppearance'

/** Composition hook: calls the sub-hooks in a fixed order (the hooks rule)
 *  and merges their partial objects into the SettingsModel bag. */
export function useSettingsModel(props: SettingsPanelProps) {
  const state = useSettingsState(props)
  const core = useSettingsCore(state)
  const features = useSettingsFeatures(state)
  const lists = useSettingsLists(state)
  // I6-1: the save orchestration sits above the partial hooks — it alone
  // decides when settings.json (the register) and engine.json (the main block)
  // get written, and what the user hears about it.
  const save = useSettingsSave(state, core, lists)
  const instant = useInstantAppearance({
    isOpen: state.isOpen,
    activeTab: state.activeTab,
    deepDraft: state.deepDraft,
    deepSections: state.deepSections,
    setDeepDraft: state.setDeepDraft,
    saveDeepSettings: lists.saveDeepSettings,
  })
  return { ...state, ...core, ...features, ...lists, ...save, ...instant }
}

export type SettingsModel = ReturnType<typeof useSettingsModel>
