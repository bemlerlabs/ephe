/**
 * The MCP catalog's documentation link leaves the shell.
 *
 * Walkthrough 2026-10-12: the catalog row rendered a plain `<a target="_blank">`.
 * Inside the desktop shell `window.open` has no way out of the web view — the
 * click did nothing (measured on the sidebar's report link, same shape). The
 * chat markdown links and the sidebar keep the `href` for the PWA and route the
 * click through `openExternally()`; the catalog link was the one that did not.
 *
 * Held here: the click reaches `openExternally` with the entry's own URL, and the
 * `href` is still on the anchor for a copy-link or a middle click.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/lib/api', () => ({ putMcpSettings: vi.fn(async () => ({})) }))
vi.mock('@/lib/nativeBrowser', () => ({ openExternally: vi.fn(async () => undefined) }))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({ i18n: { language: 'en' }, t: (key: string) => key }),
}))

import { openExternally } from '@/lib/nativeBrowser'
import { renderMcp } from './sections-mcp'
import type { SettingsModel } from './types'

const DOCS = 'https://example.com/mcp-docs'

function mcpModel() {
  return {
    t: (key: string) => key,
    i18n: { language: 'en' },
    mcpServers: [],
    mcpTools: [],
    mcpSource: 'file',
    mcpLoading: false,
    mcpSaving: false,
    mcpHealthLoading: false,
    mcpHealth: {},
    mcpCatalogQuery: '',
    mcpCatalog: [
      {
        id: 'demo',
        name: 'Demo',
        description: 'Beschreibung',
        description_en: 'Description',
        category: 'tools',
        docs: DOCS,
      },
    ],
    handleMcpHealthCheck: vi.fn(),
    setMcpCatalogQuery: vi.fn(),
    setMcpHealth: vi.fn(),
    setMcpSaving: vi.fn(),
    setMcpServers: vi.fn(),
    setMcpSource: vi.fn(),
    setMcpTools: vi.fn(),
  } as unknown as SettingsModel
}

describe('the MCP catalog documentation link', () => {
  it('routes its click through the shell and keeps the href for the PWA', () => {
    render(<>{renderMcp(mcpModel())}</>)
    const link = screen.getByTestId('mcp-catalog-docs-demo')
    expect(link.getAttribute('href')).toBe(DOCS)
    fireEvent.click(link)
    expect(openExternally).toHaveBeenCalledWith(DOCS)
  })
})
