import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { StepPill } from './StepPill'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      key === 'chat.stepPill' ? `Step ${values?.n} / ${values?.total}` : key,
  }),
}))

describe('StepPill', () => {
  it('names the running step over the transcript', () => {
    render(<StepPill step={13} total={21} onJump={() => {}} />)
    expect(screen.getByTestId('step-pill').textContent).toContain('Step 13 / 21')
  })

  it('stays away when the plan is a single step', () => {
    const { container } = render(<StepPill step={1} total={1} onJump={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('clamps a step number the plan no longer carries', () => {
    render(<StepPill step={99} total={4} onJump={() => {}} />)
    expect(screen.getByTestId('step-pill').textContent).toContain('Step 4 / 4')
  })

  it('jumps to the live edge on a click', () => {
    const onJump = vi.fn()
    render(<StepPill step={2} total={5} onJump={onJump} />)
    fireEvent.click(screen.getByTestId('step-pill'))
    expect(onJump).toHaveBeenCalledTimes(1)
  })
})
