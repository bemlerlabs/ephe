/**
 * The register's one state (register #107): what a person who has never chosen gets, and
 * what a choice survives.
 *
 * The module reads its seed when it is first imported, so each case installs the values
 * first and asks for a fresh copy of the module afterwards — the alternative is a test
 * that passes because a previous file happened to leave the value it wanted.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'

const OPEN_KEY = 'ephe.register.open'

async function fresh() {
  vi.resetModules()
  return await import('@/lib/taskRegister')
}

beforeEach(() => {
  localStorage.clear()
})

describe('the task register', () => {
  it('starts folded: the rail alone is the left edge until a person asks for the list', async () => {
    const mod = await fresh()
    expect(mod.registerOpen()).toBe(false)
  })

  it('the old column key is not a choice about this layout', async () => {
    localStorage.setItem('ephe-sidebar-collapsed', '0')
    const mod = await fresh()
    expect(mod.registerOpen()).toBe(false)
  })

  it('remembers the person who opened it, and the person who put it away', async () => {
    const mod = await fresh()
    mod.setRegisterOpen(true)
    expect(localStorage.getItem(OPEN_KEY)).toBe('1')
    expect((await fresh()).registerOpen()).toBe(true)

    mod.toggleRegister()
    expect(mod.registerOpen()).toBe(false)
    expect((await fresh()).registerOpen()).toBe(false)
  })

  it('moves the component that reads it, and leaves it alone when nothing moved', async () => {
    const mod = await fresh()
    const renders: boolean[] = []
    function Probe() {
      renders.push(mod.useRegisterOpen())
      return null
    }
    render(<Probe />)
    expect(renders.at(-1)).toBe(false)

    act(() => mod.setRegisterOpen(true))
    expect(renders.at(-1)).toBe(true)

    const before = renders.length
    act(() => mod.setRegisterOpen(true))
    expect(renders.length).toBe(before)
  })
})
