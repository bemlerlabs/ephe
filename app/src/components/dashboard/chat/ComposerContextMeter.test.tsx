import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import ComposerContextMeter from './ComposerContextMeter'

// F3: the ring shows roughly how full the window is; this shows the numbers
// and offers the one action that frees them.

describe('the composer context meter', () => {
  it('writes the fill in percent and tokens, in a tabular column', () => {
    render(<ComposerContextMeter percent={22} used={1840} window={8192} onCompact={vi.fn()} />)
    const meter = screen.getByTestId('composer-context-meter')
    expect(meter.textContent).toContain('22% · 1,840 / 8,192 tok')
    expect(meter.className).toContain('tabular')
  })

  it('says "<1 %" while the fill is real but rounds to zero', () => {
    render(<ComposerContextMeter percent={0.09} used={955} window={1048576} onCompact={vi.fn()} />)
    expect(screen.getByTestId('composer-context-numbers').textContent).toContain('<1%')
    expect(screen.getByTestId('composer-context-numbers').textContent).not.toContain('0%')
  })

  it('sends /compact through the slash channel', () => {
    const onCompact = vi.fn()
    render(<ComposerContextMeter percent={22} used={1840} window={8192} onCompact={onCompact} />)
    fireEvent.click(screen.getByTestId('composer-compact'))
    expect(onCompact).toHaveBeenCalledTimes(1)
  })

  it('stays out of the row while the window is untouched', () => {
    render(<ComposerContextMeter percent={null} used={0} window={8192} onCompact={vi.fn()} />)
    expect(screen.queryByTestId('composer-context-meter')).toBeNull()
  })

  it('stays out of the row without token numbers', () => {
    render(<ComposerContextMeter percent={22} used={null} window={null} onCompact={vi.fn()} />)
    expect(screen.queryByTestId('composer-context-meter')).toBeNull()
  })
})
