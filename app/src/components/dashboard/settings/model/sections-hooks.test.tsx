// I6-4: the Hooks range — it shows the read side of the core, inventing
// nothing: events without a caller stand there as such, status gets translated.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { HooksSection } from './sections-hooks'
import type { SettingsModel } from './types'
import type { HooksView } from '@/lib/api'

const view: HooksView = {
  enabled: true,
  path: '/Users/x/.ephe/hooks.json',
  exists: true,
  events: [
    {
      key: 'pre_tool',
      live: true,
      hooks: [{ command: '/usr/bin/log.sh', match: '*', priority: 100 }],
    },
    { key: 'post_tool', live: true, hooks: [] },
    {
      key: 'session_start',
      live: false,
      hooks: [{ command: 'echo hi', match: 'x', priority: 5 }],
    },
  ],
  recent: [
    { ts: '2026-10-04T06:00:00.000+00:00', tool: 'read_file', status: 'blocked', detail: 'policy' },
    { ts: '2026-10-04T06:00:01.000+00:00', tool: 'shell', status: 'ok', detail: '' },
  ],
}

const registerSections = [
  {
    key: 'hooks',
    fields: [
      {
        key: 'hooks.enabled',
        type: 'bool',
        label: 'Hooks ausführen',
        labelEn: 'Run hooks',
        default: true,
        value: true,
        hint: 'Aus führt keinen der Befehle aus hooks.json mehr aus.',
        hintEn: 'Off runs none of the commands in hooks.json.',
      },
    ],
  },
]

function model(over: Record<string, unknown> = {}) {
  return {
    // like the other panel tests: the key comes back, the params hang off it —
    // this line is therefore also the proof for `match`/`count`
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    deepSections: registerSections,
    deepDraft: {},
    setDeepField: () => {},
    hooksLoading: false,
    hooksView: view,
    ...over,
  } as unknown as SettingsModel
}

describe('HooksSection', () => {
  it('title, purpose and the one switch from the register', () => {
    render(<HooksSection model={model()} />)
    expect(screen.getByTestId('page-title').textContent).toBe('settings.hooksTitle')
    expect(screen.getByTestId('page-subtitle').textContent).toBe('settings.hooksHint')
    expect(screen.getByTestId('deep-row-hooks.enabled')).toBeTruthy()
    expect(screen.getByTestId('setting-switch-hooks.enabled')).toBeTruthy()
  })

  it('the file with its path and its real state', () => {
    render(<HooksSection model={model()} />)
    const row = screen.getByTestId('hooks-file')
    expect(row.textContent).toContain('/Users/x/.ephe/hooks.json')
    expect(row.textContent).toContain('settings.hooksFileExists')
  })

  it('one group per event, the command with template and order', () => {
    render(<HooksSection model={model()} />)
    expect(screen.getByTestId('hooks-group-pre_tool').textContent).toContain('/usr/bin/log.sh')
    // match '*' means: all tools — no star that speaks for itself
    expect(screen.getByTestId('hooks-group-pre_tool').textContent).toContain(
      'settings.hooksMatchAll',
    )
    // an empty event states that, instead of inventing a card
    expect(screen.getByTestId('hooks-empty-post_tool').textContent).toContain(
      'settings.hooksNoneTitle',
    )
  })

  it('events without a production caller are named as such', () => {
    render(<HooksSection model={model()} />)
    expect(screen.getByTestId('hooks-idle-session_start').textContent).toContain(
      'settings.hooksIdleHint',
    )
  })

  it('the recent runs with a translated status over the raw word', () => {
    render(<HooksSection model={model()} />)
    const blocked = screen.getByTestId('hooks-recent-0')
    expect(blocked.textContent).toContain('settings.hookStatus.blocked')
    expect(blocked.textContent).toContain('read_file')
    expect(blocked.textContent).toContain('policy')
    expect(screen.getByTestId('hooks-recent-1').textContent).toContain('settings.hookStatus.ok')
  })

  it('without a view: a loading line, then an honest error over an empty card', () => {
    render(<HooksSection model={model({ hooksView: null, hooksLoading: true })} />)
    expect(screen.getByText('settings.hooksLoading')).toBeTruthy()
    render(<HooksSection model={model({ hooksView: null, hooksLoading: false })} />)
    expect(screen.getByTestId('hooks-load-failed')).toBeTruthy()
  })
})
