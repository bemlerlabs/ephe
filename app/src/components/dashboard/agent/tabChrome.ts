'use client'

import { useTranslation } from 'react-i18next'
import { Tab } from './primitives'

// P2-A: a hover-tip fallback only for the new tab, until the locales are filled in
// (the tabTip* keys of the established tabs already exist in de/en).
const TAB_TIP_FALLBACK: Partial<Record<Tab, { title: string; body: string }>> = {
  browser: { title: 'Browser', body: 'Open any website inside the panel' },
}

function tipKey(key: Tab, part: 'title' | 'body') {
  return `agentPanel.tabTip${key.charAt(0).toUpperCase() + key.slice(1)}.${part}`
}

/** The agent run counters belong in the tab labels (terminal/git). */
export function useTabLabels(counts: { terminal: number; git: number }): Record<Tab, string> {
  const { t } = useTranslation()
  return {
    preview: t('agentPanel.tabPreview'),
    terminal: `${t('agentPanel.tabTerminal')}${counts.terminal ? ` (${counts.terminal})` : ''}`,
    git: `${t('agentPanel.tabGit')}${counts.git ? ` (${counts.git})` : ''}`,
    files: t('agentPanel.tabFiles'),
    audit: t('agentPanel.tabAudit'),
    trajectory: t('agentPanel.tabTrajectory'),
    subagents: t('agentPanel.tabSubagents'),
    memory: t('agentPanel.tabMemory'),
    browser: t('agentPanel.tabBrowser', { defaultValue: 'Browser' }),
    side: t('agentPanel.tabSide', { defaultValue: 'Side conversation' }),
  }
}

export function useTabTips(): (key: Tab) => { title: string; body: string } {
  const { t } = useTranslation()
  return (key: Tab) => ({
    title: t(tipKey(key, 'title'), { defaultValue: TAB_TIP_FALLBACK[key]?.title }),
    body: t(tipKey(key, 'body'), { defaultValue: TAB_TIP_FALLBACK[key]?.body }),
  })
}
