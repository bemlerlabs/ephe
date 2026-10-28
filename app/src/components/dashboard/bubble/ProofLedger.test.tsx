import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@/i18n'

const mode = vi.hoisted(() => ({ value: 'expanded' }))
vi.mock('@/lib/deepSettings', () => ({ useDeepSelect: () => mode.value }))

import { ProofLedger } from './ProofLedger'
import type { ToolCall } from '@/types'

const call = (over: Partial<ToolCall>): ToolCall => ({
  id: 'c1',
  name: 'run_shell',
  args: { command: 'pytest -q' },
  status: 'completed',
  ...over,
})

describe('the proof ledger', () => {
  it('lists each finished run with its tool, duration and digest in expert mode', () => {
    mode.value = 'expanded'
    render(
      <ProofLedger
        tools={[
          call({ duration_ms: 412, sha256: '9f86d0818c0f2f4d' }),
          call({ id: 'c2', name: 'read_file', args: { path: 'a.txt' }, duration_ms: 8 }),
        ]}
      />,
    )
    const rows = screen.getAllByTestId(/^proof-run-/)
    expect(rows).toHaveLength(2)
    expect(rows[0]!.textContent).toContain('[run_shell]')
    expect(rows[0]!.textContent).toContain('pytest -q')
    expect(rows[0]!.textContent).toContain('passed')
    expect(rows[0]!.textContent).toContain('412 ms')
    expect(rows[0]!.textContent).toContain('sha256:9f86d081')
    // a run whose frame carried no digest says so instead of inventing one
    expect(rows[1]!.textContent).toContain('sha256:—')
  })

  it('keeps the everyday reader at one sentence per run', () => {
    mode.value = 'collapsed'
    render(<ProofLedger tools={[call({ duration_ms: 400 })]} />)
    const row = screen.getByTestId('proof-run-c1')
    expect(row.textContent).toContain('Automatic check passed')
    expect(row.textContent).toContain('(0.4 s)')
    expect(row.textContent).not.toContain('sha256')
  })

  it('names a failed run in both registers', () => {
    mode.value = 'collapsed'
    const { unmount } = render(<ProofLedger tools={[call({ status: 'failed' })]} />)
    expect(screen.getByTestId('proof-run-c1').textContent).toContain('Check failed')
    expect(screen.getByTestId('proof-run-c1').getAttribute('data-ok')).toBe('false')
    unmount()

    mode.value = 'expanded'
    render(<ProofLedger tools={[call({ status: 'failed' })]} />)
    expect(screen.getByTestId('proof-run-c1').textContent).toContain('failed')
  })

  it('stays away while nothing has finished', () => {
    render(<ProofLedger tools={[call({ status: 'pending' }), call({ id: 'c2', status: 'waiting' })]} />)
    expect(screen.queryByTestId('proof-ledger')).toBeNull()
  })

  it('clips a long argument so one run stays one line', () => {
    const long = 'x'.repeat(60)
    render(<ProofLedger tools={[call({ args: { command: long } })]} />)
    const text = screen.getByTestId('proof-run-c1').textContent ?? ''
    expect(text).toContain(`${'x'.repeat(40)}…`)
    expect(text).not.toContain('x'.repeat(41))
  })
})
