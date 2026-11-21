import { useNavigate, useParams } from 'react-router-dom'

import SettingsPanel from '@/components/dashboard/SettingsPanel'
import { NAV_KEYS } from '@/components/dashboard/settings/types'
import type { TabKey } from '@/components/dashboard/settings/types'

const VALID: readonly TabKey[] = [...NAV_KEYS, 'about']

/** Route host for a settings section: `#/settings/agents` opens the register there. */
export default function SettingsPage() {
  const { tab } = useParams()
  const navigate = useNavigate()
  const initialTab = VALID.includes(tab as TabKey) ? (tab as TabKey) : 'engine'
  return <SettingsPanel isOpen initialTab={initialTab} onClose={() => navigate('/')} />
}
