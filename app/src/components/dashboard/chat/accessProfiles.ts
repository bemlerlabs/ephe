/**
 * The approval profiles, in the server's order and with the settings' own names.
 *
 * One table, two surfaces: the composer's access control writes the profile and
 * Settings → Security keeps the same four rows. `VALID_APPROVAL_PROFILES`
 * (`core/security_config.py`) is the authority; a fifth value would land here
 * first and in the server second, which is why this list is the client mirror.
 */

export const ACCESS_PROFILES = [
  { key: 'strict', labelKey: 'settings.profileStrict' },
  { key: 'session', labelKey: 'settings.profileSession' },
  { key: 'plan', labelKey: 'settings.profilePlan' },
  { key: 'full', labelKey: 'settings.profileFull' },
] as const

export type AccessProfile = (typeof ACCESS_PROFILES)[number]['key']

export function isAccessProfile(value: string): value is AccessProfile {
  return ACCESS_PROFILES.some((entry) => entry.key === value)
}
