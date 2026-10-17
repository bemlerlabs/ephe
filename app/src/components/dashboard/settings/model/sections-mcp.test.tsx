// I7-4: the MCP section speaks the interface's language — including the
// backend texts from core/mcp_catalog.py, and the group headers state what
// saving does to the list.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { renderMcp } from './sections-mcp'
import type { SettingsModel } from './types'
import type { McpCatalogEntry } from '@/lib/api'

const entries: McpCatalogEntry[] = [
  {
    id: 'mcp-fetch',
    name: 'Fetch Server',
    description: 'Webseiten abrufen und in Markdown konvertieren.',
    description_en: 'Fetch websites and convert them to Markdown.',
    category: 'web',
    install_hint: 'uvx mcp-server-fetch (stdio)',
  },
]

function model(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    handleMcpHealthCheck: () => {},
    mcpCatalog: entries,
    mcpCatalogQuery: '',
    mcpHealth: {},
    mcpHealthLoading: false,
    mcpLoading: false,
    mcpSaving: false,
    mcpServers: ['stdio:uvx mcp-server-fetch'],
    mcpSource: 'file',
    mcpTools: ['mcp_fetch'],
    setMcpCatalogQuery: () => {},
    setMcpHealth: () => {},
    setMcpSaving: () => {},
    setMcpServers: () => {},
    setMcpSource: () => {},
    setMcpTools: () => {},
    ...over,
  } as unknown as SettingsModel
}

describe('MCP-Bereich (I7-4)', () => {
  it('deutsche Oberflaeche: deutsche Katalogbeschreibung', () => {
    render(renderMcp(model()))
    expect(screen.getByTestId('mcp-catalog-row-mcp-fetch').textContent).toContain(
      'Webseiten abrufen',
    )
  })

  it('englische Oberflaeche: keine deutschen Saetze im Katalog', () => {
    render(renderMcp(model({ i18n: { language: 'en' } })))
    const row = screen.getByTestId('mcp-catalog-row-mcp-fetch')
    expect(row.textContent).toContain('Fetch websites')
    expect(row.textContent).not.toContain('Webseiten abrufen')
  })

  it('die Gruppen erklären Ersetzen und Nicht-Aktualisieren', () => {
    render(renderMcp(model()))
    expect(screen.getByTestId('mcp-section-servers').textContent).toContain(
      'settings.mcpGroupServersHint',
    )
    expect(screen.getByTestId('mcp-section-catalog').textContent).toContain(
      'settings.mcpCatalogHint',
    )
    expect(screen.getByText('settings.mcpToolsHint')).toBeTruthy()
  })

  it('fehlende englische Fassung faellt auf den Backend-Text zurueck', () => {
    render(
      renderMcp(
        model({
          i18n: { language: 'en' },
          mcpCatalog: [{ ...entries[0], description_en: undefined }],
        }),
      ),
    )
    expect(screen.getByTestId('mcp-catalog-row-mcp-fetch').textContent).toContain(
      'Webseiten abrufen',
    )
  })
})
