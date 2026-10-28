import { afterEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { takeChatSeed } from '@/lib/chatSeed'
import type { MarketPlugin } from '@/lib/api'
import type { SettingsModel } from '../types'
import { MarketCard } from './MarketCard'

const t = ((key: string) => key) as SettingsModel['t']

const plugin: MarketPlugin = {
  name: 'documents',
  displayName: 'Documents',
  description: 'Local documents.',
  publisher: { name: 'Ephe', verified: true },
  trust: 'bundled',
  quality_label: 'plugin',
  provenance: 'first-party',
  categories: ['documents'],
  versions: [
    {
      version: '1.1.0',
      publishTimestamp: 0,
      source: { type: 'zip', url: 'artifacts/documents.zip', sha256: 'a'.repeat(64) },
      engines: { ephe: '>=0.1.3' },
      permissions: { tool_families: ['read'], data_roots: [] },
      components: ['commands'],
    },
  ],
}

function renderCard(installed = true) {
  return render(
    <MarketCard
      plugin={plugin}
      installed={
        installed
          ? {
              name: 'documents',
              version: '1.1.0',
              description: 'Local documents.',
              enabled: true,
              origin: 'user',
              components: ['commands'],
              permissions: { tool_families: ['read'], data_roots: [] },
            }
          : undefined
      }
      language="en"
      t={t}
      busy={false}
      onInstall={() => {}}
      onRemove={() => {}}
      onRollback={() => {}}
      onSwitch={() => {}}
      consent={null}
    />,
  )
}

afterEach(() => {
  window.location.hash = ''
  takeChatSeed()
})

describe('MarketCard', () => {
  it('always draws the shared PluginIcon tile', () => {
    renderCard()
    const icon = screen.getByTestId('plugin-icon-documents')
    expect(icon.tagName).toBe('IMG')
    expect(icon.getAttribute('src')).toBe('/api/plugins/icon/documents')
  })

  it('uses the shared switch with the marketplace testid', () => {
    renderCard()
    const toggle = screen.getByTestId('market-switch-documents')
    expect(toggle.getAttribute('role')).toBe('switch')
    expect(toggle.getAttribute('aria-checked')).toBe('true')
  })

  it('keeps every badge at or above the 12 px floor', () => {
    const { container } = renderCard()
    expect(container.innerHTML).not.toContain('text-ui-2xs')
  })

  it('hands a concrete example to a fresh chat in one click', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('market-try-documents'))
    expect(takeChatSeed()).toContain('documents')
    expect(window.location.hash).toBe('#/chat')
  })
})
