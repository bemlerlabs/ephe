import { describe, expect, it } from 'vitest'
import { pointerToViewport } from './browserPointer'

const frame = { viewportWidth: 1280, viewportHeight: 800 }

describe('a click on the cast maps into the page', () => {
  it('maps the centre of a fitted picture to the centre of the viewport', () => {
    expect(
      pointerToViewport(frame, { left: 0, top: 0, width: 640, height: 400 }, 320, 200),
    ).toEqual({ x: 640, y: 400 })
  })

  it('ignores a click in the margin beside the page', () => {
    expect(
      pointerToViewport(frame, { left: 0, top: 0, width: 1000, height: 400 }, 10, 200),
    ).toBeNull()
  })
})
