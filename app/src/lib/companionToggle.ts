/**
 * QD-005 — the one switch every summon path shares.
 *
 * The header toggle, the `/companion` slash command and the `CmdOrCtrl+Shift+C`
 * chord all flip `appearance.companion_enabled`; they call this instead of each
 * carrying the register write, so the three paths cannot drift.
 */
import { getSettings, saveSections } from '@/lib/api'
import { seedDeepSettings } from '@/lib/deepSettings'

/** Flips the companion switch; resolves with the new state (false when the write failed). */
export async function toggleCompanionEnabled(): Promise<boolean> {
  try {
    const settings = await getSettings()
    const appearance = (settings.deep ?? []).find((section) => section.key === 'appearance')
    if (!appearance) throw new Error('appearance register missing')
    const values: Record<string, string | number | boolean> = {}
    for (const field of appearance.fields) {
      values[field.key] = field.value ?? field.default ?? ''
    }
    const current = Boolean(values['appearance.companion_enabled'])
    const next = !current
    values['appearance.companion_enabled'] = next
    await saveSections({ appearance: values })
    seedDeepSettings(
      (settings.deep ?? []).map((section) =>
        section.key === 'appearance'
          ? {
              ...section,
              fields: section.fields.map((field) =>
                field.key === 'appearance.companion_enabled' ? { ...field, value: next } : field,
              ),
            }
          : section,
      ),
    )
    return next
  } catch {
    return false
  }
}
