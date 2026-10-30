/**
 * WS3-20 responsive/mobile pass.
 *
 * jsdom has no layout engine, so these pin the Tailwind contract that keeps each
 * overlay inside a phone viewport — the class that makes the surface usable
 * instead of the pixel result. Each assertion fails if the responsive class is
 * dropped again.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui'
import CommandPalette from '@/components/ui/CommandPalette'
import { MarkdownBody } from '@/components/dashboard/bubble/messageMarkdown'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('responsive pass — overlays stay inside the phone viewport', () => {
  it('dialog content keeps a 1rem edge inset and a scroll cap', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>t</DialogTitle>
          <p>body</p>
        </DialogContent>
      </Dialog>,
    )
    const cls = String(screen.getByRole('dialog').className)
    expect(cls).toContain('w-[calc(100vw-2rem)]')
    expect(cls).toContain('max-h-[90dvh]')
    expect(cls).toContain('overflow-y-auto')
  })

  it('command palette keeps a horizontal inset and a dynamic-viewport cap', () => {
    const { container } = render(
      <CommandPalette
        open
        query=""
        setQuery={() => {}}
        inputRef={{ current: null }}
        grouped={{}}
        t={((k: string) => k) as never}
        onClose={() => {}}
        onSelect={() => {}}
      />,
    )
    const overlay = container.querySelector('[role="dialog"]')
    expect(overlay).toBeTruthy()
    expect(String(overlay!.className)).toContain('px-3')
    expect(String(overlay!.className)).toContain('pt-[20dvh]')
  })

})

describe('responsive pass — wide markdown does not clip on a phone', () => {
  it('wraps a GFM table in a horizontal scroll container', () => {
    render(<MarkdownBody text={'| a | b |\n| --- | --- |\n| 1 | 2 |'} highlight={false} />)
    const table = screen.getByRole('table')
    const wrap = table.parentElement
    expect(wrap).toBeTruthy()
    expect(String(wrap!.className)).toContain('overflow-x-auto')
  })
})
