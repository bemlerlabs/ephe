import type { SettingsModel } from '../types'

type T = SettingsModel['t']

export function trustLabel(trust: string, t: T): string {
  if (trust === 'bundled') return t('settings.marketKindBundled')
  if (trust === 'local') return t('settings.marketTrustLocal')
  if (trust === 'official') return t('settings.marketTrustOfficial')
  if (trust === 'verified') return t('settings.marketTrustVerified')
  if (trust === 'community') return t('settings.marketTrustCommunity')
  return trust
}
