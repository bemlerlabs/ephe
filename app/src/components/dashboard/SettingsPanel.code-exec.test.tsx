// I6-5: the code execution card is an area of its own — and it stays purely
// read-only. The three tests came from SettingsPanel.privacy.test.tsx, where the
// card used to sit between the approval profile and the local-data button.
import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import { CodeExecSection } from './settings/model/sections-code-exec'
import type { SettingsModel } from './settings/model/types'
import type { CodeExecPolicy } from '@/lib/api'

// The policy as the server delivers it — the same values that
// core/cpython_cell.py writes into the WASIConfig.
const codeExecPolicy: CodeExecPolicy = {
  runtime: 'cpython-cell',
  max_fuel: 20000000000,
  max_memory_mb: 256,
  timeout_seconds: 30,
  io_cpu_seconds: 20,
  io_budget_bytes: 67108864,
  disk_quota_bytes: 33554432,
  work_quota_bytes: 67108864,
  quota_scopes: {
    disk_quota_bytes: 'je Datei — durchgesetzt von der Engine (RLIMIT_FSIZE, EFBIG)',
    work_quota_bytes: 'je Session ueber alle Dateien — durchgesetzt von ephe (sweep_work_dir)',
    io_budget_bytes: 'nur der Sandbox-Ordner der Engine, nicht /work — meldet hier stets 0',
  },
  output_cap_bytes: 10000,
  sink_ceiling_bytes: 10000,
  guest_forward_bytes: 2048,
  guest_tee_cap_bytes: 524288,
  preopens: ['/work (beschreibbar, je Session)', 'stdio/gast-root (nur gelesen)'],
  network: 'none',
  guest: {
    version: '3.13.16',
    installed: true,
    library: true,
    entry_hash_ok: true,
    stdlib_hash_ok: true,
    path: '/Users/x/.ephe/cells/cpython-wasi-3.13.16',
    reason: '',
  },
  license: { guest: 'PSF-2.0', cell_runtime: 'Apache-2.0 (ephemora-cell 1.0.4.3)' },
  measured: { boot_fuel: 1418000000 },
  gaps: ['kein Netzwerk'],
}

function model(policy: CodeExecPolicy | null) {
  return {
    // Keys returned and the parameters behind them — otherwise nothing evidences
    // what a description states (e.g. the license of the guest).
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    codeExecCfg: policy,
  } as unknown as SettingsModel
}

describe('Bereich Code-Ausführung (I6-5)', () => {
  it('zeigt die wirksamen Deckel read-only', () => {
    render(<CodeExecSection model={model(codeExecPolicy)} />)
    const card = screen.getByTestId('code-exec-policy')
    // The runtime is stated because the server measured it — not because the UI guesses.
    expect(within(card).getByTestId('code-exec-runtime').textContent).toContain('cpython-cell')
    expect(within(card).getByTestId('code-exec-integrity').textContent).toContain(
      'settings.codeExecIntegrityOk',
    )
    expect(within(card).getByTestId('code-exec-fuel').textContent).toContain('20.000.000.000')
    expect(within(card).getByTestId('code-exec-memory').textContent).toContain('256 MB')
    // The two disk rows are the point: 32 MiB apply per file, the
    // session-wide ceiling is a second, higher number — the card must no
    // longer show them as a single quota.
    expect(within(card).getByTestId('code-exec-disk').textContent).toContain('32 MiB')
    expect(within(card).getByTestId('code-exec-work').textContent).toContain('64 MiB')
    expect(within(card).getByTestId('code-exec-output').textContent).toContain('10.000 bytes')
    // The pass-through is not the wall: the card names both numbers.
    expect(within(card).getByTestId('code-exec-journal').textContent).toContain('2.048 live ·')
    expect(within(card).getByTestId('code-exec-journal').textContent).toContain(
      '512 KiB /work/stdout.log',
    )
    expect(within(card).getByTestId('code-exec-guest').textContent).toContain('PSF-2.0')
    expect(within(card).getByTestId('code-exec-guest').textContent).toContain('CPython 3.13.16')
    // No reason text for an intact guest …
    expect(within(card).queryByTestId('code-exec-reason')).not.toBeInTheDocument()
    // … and no new secret surface: the area is purely read-only.
    expect(within(card).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(card).queryByRole('button')).not.toBeInTheDocument()
    // Network: no switch, no claim of a mode.
    expect(within(card).getByTestId('code-exec-network').textContent).toContain(
      'settings.codeExecNetworkNone',
    )
  })

  it('ein Server ohne Journal-Zahlen lässt die Zeile weg, statt NaN zu zeigen', () => {
    const { guest_forward_bytes, guest_tee_cap_bytes, sink_ceiling_bytes, ...older } =
      codeExecPolicy
    void guest_forward_bytes
    void guest_tee_cap_bytes
    void sink_ceiling_bytes
    render(<CodeExecSection model={model(older as CodeExecPolicy)} />)
    const card = screen.getByTestId('code-exec-policy')
    expect(within(card).queryByTestId('code-exec-journal')).not.toBeInTheDocument()
    expect(within(card).getByTestId('code-exec-output')).toBeInTheDocument()
  })

  it('ein Grund des Gasts wird angezeigt, die Karte bleibt lesend', () => {
    render(
      <CodeExecSection
        model={model({
          ...codeExecPolicy,
          runtime: 'kernel',
          guest: {
            ...codeExecPolicy.guest,
            installed: false,
            entry_hash_ok: false,
            stdlib_hash_ok: false,
            reason: 'CPython-Gast nicht installiert',
          },
        })}
      />,
    )
    const card = screen.getByTestId('code-exec-policy')
    expect(within(card).getByTestId('code-exec-runtime').textContent).toContain('kernel')
    expect(within(card).getByTestId('code-exec-reason').textContent).toContain('nicht installiert')
    expect(within(card).getByTestId('code-exec-integrity').textContent).toContain(
      'settings.codeExecIntegrityBad',
    )
  })

  it('ohne Policy: Ladezeile statt erfundener Zahlen', () => {
    render(<CodeExecSection model={model(null)} />)
    expect(screen.getByTestId('code-exec-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('code-exec-policy')).not.toBeInTheDocument()
  })
})
