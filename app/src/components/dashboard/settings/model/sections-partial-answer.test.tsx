// D0-4: a settings area whose endpoint answers partially still has a state to show.
//
// The theme sweep could not measure seven surfaces because the route fell over into
// PageErrorBoundary first: Voice, Persona, Hooks, Cron, Network and Code execution each
// read a nested field of their answer as if every server had sent it, and `/workspaces`
// projected a change-set file that carries no digest. A beta.8 backend answering a
// beta.9 front end is the same shape in the field, so the guard belongs in the read.
// These are the thin answers, one section at a time.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { CodeExecSection } from './sections-code-exec'
import { HooksSection } from './sections-hooks'
import { NetworkSection } from './sections-network'
import { VoiceSection } from './sections-voice'
import type { SettingsModel } from './types'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key} ${JSON.stringify(opts)}` : key

function model(over: Record<string, unknown>) {
  return {
    t,
    i18n: { language: 'en' },
    deepSections: [],
    deepDraft: {},
    setDeepField: () => {},
    ...over,
  } as unknown as SettingsModel
}

describe('settings areas on a partial answer (D0-4)', () => {
  it('Voice lists no installed voices instead of reading a missing list', () => {
    render(
      <VoiceSection
        model={model({
          voiceCfg: { tts_engine: 'piper', piper_voice: '', edge_voice: '' },
          autoSpeak: false,
          voiceMsg: '',
          handleVoiceSave: async () => {},
          setVoiceCfg: () => {},
          setAutoSpeak: () => {},
          testVoice: async () => {},
        })}
      />,
    )
    expect(screen.getByTestId('voice-row-installed').textContent).toContain(
      'settings.piperInstallHint',
    )
  })

  it('Hooks shows the no-hook row for an event the server reports empty', () => {
    render(
      <HooksSection
        model={model({
          hooksLoading: false,
          hooksView: {
            enabled: true,
            path: '/Users/x/.ephe/hooks.json',
            exists: true,
            events: [{ key: 'pre_tool', live: true }],
          },
        })}
      />,
    )
    expect(screen.getByTestId('hooks-empty-pre_tool').textContent).toContain(
      'settings.hooksNoneHint',
    )
    expect(screen.getByTestId('hooks-recent-empty')).toBeTruthy()
  })

  it('Hooks stays on the page for the payload an older backend sends', () => {
    // A beta.8 server names its event fields `name`/`matched` and its run fields
    // `event`/`ok`/`at`. Nothing there is a hook the area can list, so it shows the
    // file row and an unnamed run instead of the crash fallback.
    render(
      <HooksSection
        model={model({
          hooksLoading: false,
          hooksView: {
            enabled: true,
            path: '~/.ephe/hooks.json',
            exists: true,
            events: [{ name: 'on_turn_end', matched: 3 }],
            recent: [{ event: 'on_turn_end', ok: true, at: '2026-10-11T08:59:00Z' }],
          },
        })}
      />,
    )
    expect(screen.getByTestId('hooks-file').textContent).toContain('~/.ephe/hooks.json')
    expect(screen.getByTestId('hooks-recent-0')).toBeTruthy()
  })

  it('Network reads the two share rows as none when the answer has no lists', () => {
    render(<NetworkSection model={model({ networkStatus: { bind_host: '127.0.0.1' } })} />)
    expect(screen.getByTestId('network-roots').textContent).toContain('—')
    expect(screen.getByTestId('network-proxy').textContent).toContain('settings.networkProxyOff')
  })

  it('Code execution calls an unreported checksum unknown, never bad', () => {
    render(<CodeExecSection model={model({ codeExecCfg: {} })} />)
    const row = screen.getByTestId('code-exec-integrity')
    expect(row.textContent).toContain('settings.codeExecIntegrityUnknown')
    expect(row.textContent).not.toContain('settings.codeExecIntegrityBad')
    expect(screen.getByTestId('code-exec-guest').textContent).toContain('—')
    expect(screen.getByTestId('code-exec-preopens').textContent).toContain('—')
  })

  it('Code execution keeps the verdict it was given', () => {
    render(
      <CodeExecSection
        model={model({
          codeExecCfg: {
            runtime: 'cell',
            guest: {
              version: '3.14',
              entry_hash_ok: true,
              stdlib_hash_ok: true,
              reason: '',
            },
            license: { guest: 'BSD-3-Clause', cell_runtime: 'BSD-3-Clause' },
            preopens: ['/work', '/tmp'],
          },
        })}
      />,
    )
    expect(screen.getByTestId('code-exec-integrity').textContent).toContain(
      'settings.codeExecIntegrityOk',
    )
    expect(screen.getByTestId('code-exec-guest').textContent).toContain('CPython 3.14')
    expect(screen.getByTestId('code-exec-preopens').textContent).toContain('/work · /tmp')
  })
})
