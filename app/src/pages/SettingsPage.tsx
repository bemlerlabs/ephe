import { useNavigate, useParams } from 'react-router-dom'

import SettingsPanel from '@/components/dashboard/SettingsPanel'
import { ensureSettingsCopy } from '@/lib/settingsCopy'
import { NAV_KEYS } from '@/components/dashboard/settings/types'
import type { TabKey } from '@/components/dashboard/settings/types'

// LS-1: the register's hints and row titles are a lazy read, opened here because this
// route is the only surface that renders them. Inside SettingsPanel the two lines of
// glue would tip that chunk over its 45.0 kB ceiling (measured 44.98 kB).
void ensureSettingsCopy()

const VALID: readonly TabKey[] = [...NAV_KEYS, 'about']

/** Route host for a settings section: `#/settings/agents` opens the register there. */
export default function SettingsPage() {
  const { tab } = useParams()
  const navigate = useNavigate()
  const initialTab = VALID.includes(tab as TabKey) ? (tab as TabKey) : 'engine'
  return <SettingsPanel isOpen initialTab={initialTab} onClose={() => navigate('/')} />
}
