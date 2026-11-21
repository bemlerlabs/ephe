import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Eye } from 'lucide-react'
import { ICON_SIZE, ICON_STROKE_WIDTH, IconScale } from './iconScale'

describe('icon scale', () => {
  it('draws a glyph with one optical stroke', () => {
    const { container } = render(
      <IconScale>
        <Eye />
      </IconScale>,
    )
    const svg = container.querySelector('svg')
    expect(svg?.getAttribute('stroke-width')).toBe(String(ICON_STROKE_WIDTH))
    expect(ICON_STROKE_WIDTH).toBe(1.5)
  })

  it('keeps the three size steps', () => {
    expect(ICON_SIZE).toEqual({ inline: 16, navigation: 18, section: 20 })
  })
})
