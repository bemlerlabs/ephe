/**
 * #39, second half — the other half of the same boot.
 *
 * `ephe.panel.dock` / `ephe.panel.width` are read by usePanelGeometry, not by the
 * tab state object, but they live in the same persisted panel state and share the
 * failure mode: dock was a cast ('middle' painted the pane on the
 * wrong edge), and width went through Number(), so Infinity or a negative
 * hand-edit survived into the style while a stored width below the drag floor was
 * accepted as if the pane had produced it.
 *
 * GIVEN  a stored dock/width with a value the pane itself can never write
 * WHEN   the geometry hook boots
 * THEN   the documented default (right / 420) comes back, without an exception
 * AND    values the pane does write come back unchanged.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePanelGeometry } from './usePanelGeometry'

const FIT_WIDTH = 420

function geometry() {
  return renderHook(() => usePanelGeometry(false)).result.current
}

describe('panel boot — ephe.panel.dock', () => {
  beforeEach(() => localStorage.clear())

  for (const stored of ['middle', '{"a":1}', 'LEFT', 'null', '']) {
    it(`falls back to the right dock for ${JSON.stringify(stored)}`, () => {
      localStorage.setItem('ephe.panel.dock', stored)
      expect(geometry().dock).toBe('right')
    })
  }

  it('keeps a valid dock side', () => {
    localStorage.setItem('ephe.panel.dock', 'left')
    expect(geometry().dock).toBe('left')
  })
})

describe('panel boot — ephe.panel.width', () => {
  beforeEach(() => localStorage.clear())

  // object/non-numeric text, Infinity (JSON can carry 1e999), a negative width,
  // zero, and an absurd hand-edit above the pane's own 60vw bound
  const badShapes = ['{"a":1}', 'abc', 'Infinity', '-100', '0', '999999', 'NaN']

  for (const stored of badShapes) {
    it(`falls back to the fit width for ${stored}`, () => {
      localStorage.setItem('ephe.panel.width', stored)
      expect(geometry().width).toBe(FIT_WIDTH)
    })
  }

  // the values drag-resize and the width cycle actually persist
  for (const width of [360, 420, 460, 560, 720]) {
    it(`keeps the valid width ${width}`, () => {
      localStorage.setItem('ephe.panel.width', String(width))
      expect(geometry().width).toBe(width)
    })
  }
})
