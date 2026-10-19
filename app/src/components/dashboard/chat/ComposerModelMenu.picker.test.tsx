// S2 host 3, completed: the composer chip menu is the shared picker now. What is
// tested here is exactly what the menu did not have before — filters, sort, the star,
// the metadata line — plus the two rules this host owns: an unknown never passes a
// filter, and a pick still speaks the (kind, model, endpoint) contract.
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within, cleanup } from '@testing-library/react'
import { createRef } from 'react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

import ComposerModelMenu from './ComposerModelMenu'
import type { ModelChipEntry } from './composerModelEntries'

const ENTRIES: ModelChipEntry[] = [
  {
    id: 'opencode:gemma4:12b',
    kind: 'openai_compatible',
    model: 'gemma4:12b',
    label: 'OpenCode · gemma4:12b',
    endpoint: 'https://api.example.test/v1',
    endpointKind: 'url',
  },
  {
    id: 'opencode:qwen:7b',
    kind: 'openai_compatible',
    model: 'qwen:7b',
    label: 'OpenCode · qwen:7b',
    endpoint: 'http://127.0.0.1:8000/v1',
    endpointKind: 'loopback',
  },
  {
    id: 'openrouter:deepseek/deepseek-chat',
    kind: 'openai_compatible',
    model: 'deepseek/deepseek-chat',
    label: 'OpenRouter · deepseek/deepseek-chat',
    endpoint: 'https://openrouter.ai/api/v1',
    endpointKind: 'url',
    context_window: 131072,
    price_in_per_m: 0,
    price_out_per_m: 0,
    is_free: true,
    supports_tools: true,
    supports_vision: false,
  },
  {
    id: 'cursor:gpt-4o',
    kind: 'openai_compatible',
    model: 'gpt-4o',
    label: 'Cursor · gpt-4o',
    endpoint: 'https://${TENANT}.example.test/v1',
    endpointKind: 'url',
    unconfigured: true,
  },
]

function renderMenu(over: Partial<Parameters<typeof ComposerModelMenu>[0]> = {}) {
  const onPick = vi.fn()
  const onClose = vi.fn()
  render(
    <ComposerModelMenu
      pos={{ left: 100, bottom: 200 }}
      anchorRef={createRef<HTMLElement>()}
      entries={ENTRIES}
      activeP=""
      model=""
      needsSetup={false}
      onClose={onClose}
      onPick={onPick}
      onSetup={vi.fn()}
      {...over}
    />,
  )
  return { onPick, onClose }
}

beforeEach(() => window.localStorage.clear())
afterEach(cleanup)

describe('the composer menu is the shared picker', () => {
  it('carries search, the four filters and the sort', () => {
    renderMenu()
    expect(screen.getByTestId('model-chip-search')).toBeTruthy()
    for (const filter of ['free', 'tools', 'vision', 'longContext']) {
      expect(screen.getByTestId(`model-chip-filter-${filter}`), filter).toBeTruthy()
    }
    expect(screen.getByTestId('model-chip-sort')).toBeTruthy()
  })

  it('keeps the chat / other / not-configured sections and their rows', () => {
    renderMenu()
    expect(screen.getByTestId('model-group-chat')).toBeTruthy()
    expect(screen.getByTestId('model-group-unconfigured')).toBeTruthy()
    expect(screen.getByTestId('model-chip-option-opencode:gemma4:12b')).toBeTruthy()
  })

  it('prints the metadata line as unknown, never as a guess', () => {
    renderMenu()
    const row = screen.getByTestId('model-chip-option-opencode:gemma4:12b')
    // A scan entry states a name and an endpoint, and nothing about price or window.
    const chips = row.querySelectorAll(
      '[data-testid="model-chip-free"], [data-testid="model-chip-tools"], [data-testid="model-chip-vision"]',
    )
    expect(chips).toHaveLength(0)
    expect((row.textContent ?? '').split('—').length - 1).toBe(2)
  })

  it('shows the endpoint as a word, not as a URL', () => {
    renderMenu()
    const row = screen.getByTestId('model-chip-option-opencode:qwen:7b')
    const titled = row.querySelector('[title]') as HTMLElement
    expect(titled.getAttribute('title')).toBe('OpenCode · qwen:7b — local')
    expect(titled.getAttribute('title')).not.toContain('127.0.0.1')
  })

  it('prints the facts the provider table stated', () => {
    renderMenu()
    const row = screen.getByTestId('model-chip-option-openrouter:deepseek/deepseek-chat')
    expect(row.textContent).toContain('131k')
    expect(within(row).getByTestId('model-chip-free').dataset.state).toBe('yes')
    expect(within(row).getByTestId('model-chip-tools').dataset.state).toBe('yes')
    expect(within(row).getByTestId('model-chip-vision').dataset.state).toBe('no')
  })

  it('cannot pull an unknown row into a filter it never answered', () => {
    renderMenu()
    fireEvent.click(screen.getByTestId('model-chip-filter-free'))
    // The stated free row stays; the scan rows that never answered drop out.
    expect(screen.getByTestId('model-chip-option-openrouter:deepseek/deepseek-chat')).toBeTruthy()
    expect(screen.queryByTestId('model-chip-option-opencode:gemma4:12b')).toBeNull()
    expect(screen.queryByTestId('model-chip-option-opencode:qwen:7b')).toBeNull()
  })

  it('remembers a favorite on the device', () => {
    renderMenu()
    const row = screen.getByTestId('model-chip-option-opencode:gemma4:12b')
    fireEvent.click(within(row).getByTestId('model-chip-option-opencode:gemma4:12b-favorite'))
    expect(JSON.parse(window.localStorage.getItem('ephe.modelPicker.favorites') ?? '[]')).toEqual([
      'gemma4:12b',
    ])
  })

  it('picks with the provider kind, the model tag and the endpoint', () => {
    const { onPick } = renderMenu()
    fireEvent.click(screen.getByTestId('model-chip-option-opencode:gemma4:12b'))
    expect(onPick).toHaveBeenCalledWith(
      'openai_compatible',
      'gemma4:12b',
      'https://api.example.test/v1',
    )
  })

  it('will not pick a row whose endpoint is still a template', () => {
    const { onPick } = renderMenu()
    fireEvent.click(screen.getByTestId('model-chip-option-cursor:gpt-4o'))
    expect(onPick).not.toHaveBeenCalled()
  })
})
