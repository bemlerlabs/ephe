/**
 * #106 — the Extensions row states how much of its ceiling a bundle has spent,
 * and the stored-file list is the move the refusal names.
 *
 * The copy is read from locales/en.json while the test runs, so a label with no
 * key behind it fails here. A host path is not a label this row may show.
 */
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getPluginState: vi.fn(),
    removePluginStateFile: vi.fn(),
  }
})

import { getPluginState, removePluginStateFile } from '@/lib/api'
import { renderPlugins } from './sections-plugins'

function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/en.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}

const EN = JSON.parse(readFileSync(resolve(findSrc(), 'locales/en.json'), 'utf8')) as {
  settings: Record<string, string>
}

function t(key: string, options?: Record<string, unknown>): string {
  const dot = key.indexOf('.')
  const namespace = dot < 0 ? '' : key.slice(0, dot)
  const leaf = dot < 0 ? key : key.slice(dot + 1)
  const table = (EN as unknown as Record<string, Record<string, string>>)[namespace] ?? {}
  const template = table[leaf] ?? key
  return template.replace(/\{\{(\w+)\}\}/g, (_match: string, name: string) =>
    String(options?.[name] ?? ''),
  )
}

function row() {
  const model = {
    t,
    pluginQuery: '',
    setPluginQuery: () => {},
    expandedPlugin: null,
    setExpandedPlugin: () => {},
    handlePluginToggle: () => {},
    handlePluginMasterToggle: () => {},
    deepSections: [],
    pluginView: {
      public: [
        {
          id: 'demo',
          name: 'Demo',
          description: 'a bundle',
          tags: [],
          example_prompts: [],
          enabled: true,
          state_usage: { used_mb: 2, cap_mb: 512, file_count: 1 },
        },
      ],
      personal: [],
      master_enabled: true,
      read_only: false,
      unproven: false,
      notices: [],
    },
  } as never
  return render(renderPlugins(model))
}

describe('the plugin row states the stored bytes and removes one file', () => {
  it('names both numbers, then removes the file the reader confirms', async () => {
    vi.mocked(getPluginState).mockResolvedValue({
      used_mb: 2,
      cap_mb: 512,
      file_count: 1,
      used_bytes: 2048,
      cap_bytes: 512 * 1024 * 1024,
      entries: [{ name: 'kept.bin', bytes: 2048 }],
      truncated: false,
    })
    vi.mocked(removePluginStateFile).mockResolvedValue({
      used_mb: 0,
      cap_mb: 512,
      file_count: 0,
      used_bytes: 0,
      cap_bytes: 512 * 1024 * 1024,
      entries: [],
      truncated: false,
    })
    row()
    expect(screen.getByTestId('plugin-state-usage-demo').textContent).toBe('2 MB of 512 MB stored')
    fireEvent.click(screen.getByTestId('plugin-state-files-demo'))
    await waitFor(() => {
      expect(screen.getByTestId('plugin-state-list-demo').textContent).toContain('kept.bin')
    })
    expect(screen.getByTestId('plugin-state-list-demo').textContent).not.toContain('/Users')
    fireEvent.click(screen.getByTestId('plugin-state-remove-demo-0'))
    expect(removePluginStateFile).not.toHaveBeenCalled()
    expect(screen.getByTestId('plugin-state-remove-demo-0').textContent).toContain(
      'Remove this file',
    )
    fireEvent.click(screen.getByTestId('plugin-state-remove-demo-0'))
    await waitFor(() => {
      expect(screen.getByTestId('plugin-state-usage-demo').textContent).toBe(
        '0 MB of 512 MB stored',
      )
    })
    expect(removePluginStateFile).toHaveBeenCalledWith('demo', 'kept.bin')
    expect(screen.getByTestId('plugin-state-list-demo').textContent).toContain('Nothing stored')
  })
})
