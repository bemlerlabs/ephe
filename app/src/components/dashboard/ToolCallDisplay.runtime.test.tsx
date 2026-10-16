/**
 * Ephe — wave E1: the agent panel shows WHICH runtime carried the code.
 *
 * GIVEN  an execute_code tool call with a cell or a kernel header
 * WHEN   ToolCallDisplay renders
 * THEN   a named runtime chip (CPython cell / kernel · unsandboxed) —
 *        the kernel is never left unnamed, the cell claims nothing unproven.
 */
import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import i18n from '@/i18n'
import ToolCallDisplay from './ToolCallDisplay'
import type { ToolCall } from '@/store/chatStore'

vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => []),
}))

function tc(partial: Partial<ToolCall> & { id: string }): ToolCall {
  return { name: 'execute_code', args: { code: 'print(1+1)' }, status: 'completed', ...partial }
}

const CELL_RESULT =
  '[execute_code] runtime=cpython-cell/3.13.16 status=OK exit=0 fuel=1418000000/20000000000 ' +
  'elapsed=948ms mem<=256MB preopens=/work net=none\nstdout:\n2\n'

const KERNEL_RESULT =
  '[execute_code] runtime=kernel status=OK runtime=kernel UNSANDBOXED — Code laeuft im ' +
  'Ephe-Prozess mit vollem Host-Zugriff (os, subprocess, Dateien, Netz)\n42\n'

afterEach(cleanup)

describe('ToolCallDisplay — Laufzeit-Chip (E1)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('benennt die CPython-Cell bei einem Cell-Lauf', () => {
    render(<ToolCallDisplay tool_calls={[tc({ id: '1', result: CELL_RESULT })]} />)
    const chip = screen.getByTestId('tool-runtime-chip')
    expect(chip.dataset.runtime).toBe('cpython-cell')
    expect(chip.textContent).toBe('CPython cell')
  })

  it('benennt den ungesandboxten Kernel beim Opt-out', () => {
    render(<ToolCallDisplay tool_calls={[tc({ id: '2', result: KERNEL_RESULT })]} />)
    const chip = screen.getByTestId('tool-runtime-chip')
    expect(chip.dataset.runtime).toBe('kernel')
    expect(chip.textContent).toBe('kernel · unsandboxed')
  })

  it('zeigt keinen Chip, wenn das Ergebnis keine Laufzeit nennt', () => {
    render(
      <ToolCallDisplay
        tool_calls={[tc({ id: '3', name: 'read_file', args: { path: '/a' }, result: 'zeile' })]}
      />,
    )
    expect(screen.queryByTestId('tool-runtime-chip')).not.toBeInTheDocument()
  })
})

describe('ToolCallDisplay — Laufzeit-Chip auf Deutsch', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('de')
  })

  afterAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('benennt den Kernel uebersetzt — kein unbenannter Unsandbox-Lauf', () => {
    render(<ToolCallDisplay tool_calls={[tc({ id: '4', result: KERNEL_RESULT })]} />)
    expect(screen.getByTestId('tool-runtime-chip').textContent).toBe('Kernel · ungesandboxet')
  })
})
