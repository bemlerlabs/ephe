'use client'

/**
 * I6-1: the one save surface.
 *
 * A section used to carry two buttons that persisted DIFFERENT things: the
 * footer wrote AppSettings (engine.json: engine, folders, language,
 * generation block), while `DeepFields` wrote the register (settings.json:
 * font, animation, chat, plugin policy) through its own button. The same
 * word "Save" for two storage areas — saving one made the other look
 * unsaved.
 *
 * Now the footer button serves both, in this order: the register first, then
 * the main block. Both are separate writes with separate error messages,
 * because one failing must not let the other appear "saved". "Saved" exists
 * only once both have got through; after success the main block reloads the
 * view, on failure the user's entries stay so that they can still be
 * corrected.
 */
import { AppSettings, updateSettings } from '@/lib/api'
import { toastBus } from '@/lib/toast'
import { countDeepChanges, generationWithOptions } from './bounds'
import type { useSettingsCore } from './useSettingsCore'
import type { useSettingsLists } from './useSettingsLists'
import type { useSettingsState } from './useSettingsState'

export function useSettingsSave(
  state: ReturnType<typeof useSettingsState>,
  core: ReturnType<typeof useSettingsCore>,
  lists: ReturnType<typeof useSettingsLists>,
) {
  const {
    customApiKey,
    customEndpoint,
    deepDraft,
    deepSections,
    genDraft,
    outputDraft,
    setSaved,
    setSaving,
    settings,
    t,
    workspaceDraft,
  } = state

  // The footer button's counter: every unsaved register change, regardless of
  // which section it arose in — the button writes them all out of whatever
  // section is currently open.
  const deepChanged = countDeepChanges(deepSections, deepDraft)

  async function saveSettings() {
    setSaving(true)
    const deep = deepChanged > 0 ? await lists.saveDeepSettings() : { ok: true }

    const chosenModel = settings?.provider.model ?? ''
    const newSettings: Partial<AppSettings> = {
      language: settings?.language,
      memory_enabled: settings?.memory_enabled,
      // F: workspace/project folder — the shell and file tools work inside it.
      workspace_dir: workspaceDraft.trim() || '',
      // R44 (P4): output path; empty = back to the Downloads default.
      output_dir: outputDraft.trim() || '',
      // Wave 5: generation block — send only set values (null fields mean
      // "keep the server default"). I3-3: the number clamps to the bound taken
      // out of the payload instead of waiting for the 422 toast.
      generation: generationWithOptions(genDraft, settings?.generation_meta),
    }

    // An engine without a tag is not a choice this panel may persist, and filling one in
    // here is what made a user read back a model nobody chose. Everything else in the
    // block still saves; the endpoint and key drafts stay unsent until a tag exists.
    if (chosenModel) {
      newSettings.provider = {
        ...(settings?.provider || {}),
        model: chosenModel,
        type: settings?.provider.type || 'local_ollama',
        endpoint: customEndpoint || undefined,
        api_key: customApiKey || undefined,
      }
    }

    let mainOk = true
    let mainDetail: string | undefined
    try {
      await updateSettings(newSettings)
    } catch (e) {
      console.error('Failed to save settings')
      mainOk = false
      mainDetail = e instanceof Error && e.message ? e.message : undefined
    }

    // Each storage area reports for itself — two failures, two toasts.
    if (!deep.ok) toastBus.error(t('settings.deepSaveFailed'), deep.detail)
    if (!mainOk) toastBus.error(t('settings.saveFailed'), mainDetail)
    if (mainOk && !chosenModel) {
      toastBus.error(t('settings.chooseModel'), t('settings.modelListHint'))
    }
    if (mainOk) core.loadSettings()
    if (mainOk && deep.ok && chosenModel) {
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      toastBus.success(t('settings.saved'), workspaceDraft.trim() || undefined)
    }
    setSaving(false)
  }

  return { saveSettings, deepChanged }
}
