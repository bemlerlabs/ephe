import { describe, it, expect, vi } from 'vitest'
import { remeasureRows } from './remeasureRows'

// R36-B regression support: after a streamed turn the virtualizer cache must
// be re-fed with the real row heights (see lib/remeasureRows.ts docstring).

describe('remeasureRows', () => {
  it('returns 0 for a missing container', () => {
    const measure = vi.fn()
    expect(remeasureRows(null, '[data-testid="row"]', measure)).toBe(0)
    expect(measure).not.toHaveBeenCalled()
  })

  it('measures every mounted row and passes the nodes in DOM order', () => {
    document.body.innerHTML = `
      <div id="scroll">
        <div data-testid="row" style="height: 40px">a</div>
        <div data-testid="row" style="height: 80px">b</div>
        <div data-testid="other">skip me</div>
      </div>
    `
    const container = document.getElementById('scroll')
    const measured: HTMLElement[] = []
    const count = remeasureRows(container, '[data-testid="row"]', (el) => measured.push(el))
    expect(count).toBe(2)
    expect(measured.map((el) => el.textContent)).toEqual(['a', 'b'])
  })

  it('keeps measuring when a row is detached mid-loop (query snapshot)', () => {
    document.body.innerHTML = `
      <div id="scroll">
        <div data-testid="row">a</div>
        <div data-testid="row">b</div>
      </div>
    `
    const container = document.getElementById('scroll')!
    const measure = vi.fn((el: HTMLElement) => {
      if (el.textContent === 'a') el.remove()
    })
    // Must not throw even though the first node detaches itself.
    expect(() => remeasureRows(container, '[data-testid="row"]', measure)).not.toThrow()
    expect(measure).toHaveBeenCalledTimes(2)
  })
})
