/**
 * Ephe — Wave E1: the card names the runtime that actually carried the code.
 *
 * GIVEN  an execute_code result whose header line is `[execute_code] runtime=…`
 * WHEN   codeRuntimeFromResult / classifyToolCall
 * THEN   cell runs show "cpython-cell", a kernel opt-out shows "kernel",
 *        everything else shows null — the panel never invents a status.
 */
import { describe, it, expect } from 'vitest'
import { classifyToolCall, codeRuntimeFromResult } from '@/lib/toolCardModel'

const CELL_HEAD =
  '[execute_code] runtime=cpython-cell/3.13.16 status=OK exit=0 fuel=1418000000/20000000000 ' +
  'elapsed=948ms mem<=256MB preopens=/work net=none\nstdout:\n2\n'

const KERNEL_HEAD =
  '[execute_code] runtime=kernel status=OK runtime=kernel UNSANDBOXED — Code laeuft im ' +
  'Ephe-Prozess mit vollem Host-Zugriff (os, subprocess, Dateien, Netz)\n42\n'

describe('codeRuntimeFromResult — Laufzeit-Nachweis', () => {
  it('erkennt die gepinnte CPython-Cell (Version wird abgeschnitten)', () => {
    expect(codeRuntimeFromResult(CELL_HEAD)).toBe('cpython-cell')
  })

  it('erkennt den Kernel-Opt-out', () => {
    expect(codeRuntimeFromResult(KERNEL_HEAD)).toBe('kernel')
  })

  it('laedt die Kopfzeile auch aus einem Ergebnis-Rumpf', () => {
    expect(codeRuntimeFromResult('whatever\n' + CELL_HEAD)).toBe('cpython-cell')
  })

  it('null ohne Marker, bei unbekannter Laufzeit und fuer leeres Ergebnis', () => {
    expect(codeRuntimeFromResult('alles gut')).toBeNull()
    expect(codeRuntimeFromResult('[execute_code] runtime=mystery status=OK')).toBeNull()
    expect(codeRuntimeFromResult(undefined)).toBeNull()
    expect(codeRuntimeFromResult('')).toBeNull()
  })
})

describe('classifyToolCall — runtime-Feld je Werkzeug', () => {
  it('execute_code tragt die Laufzeit des Turns', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'execute_code',
      args: { code: 'print(1+1)' },
      result: CELL_HEAD,
      status: 'completed',
    })
    expect(m.runtime).toBe('cpython-cell')
  })

  it('execute_code im Kernel-Opt-out zeigt kernel', () => {
    const m = classifyToolCall({
      id: '2',
      name: 'execute_code',
      args: { code: 'print(42)' },
      result: KERNEL_HEAD,
      status: 'completed',
    })
    expect(m.runtime).toBe('kernel')
  })

  it('nicht.Code-Werkzeuge haben keine Laufzeit-Chip', () => {
    const m = classifyToolCall({
      id: '3',
      name: 'run_shell',
      args: { command: 'ls' },
      result: 'ok\n[exit 0]',
      status: 'completed',
    })
    expect(m.runtime).toBeNull()
  })
})
