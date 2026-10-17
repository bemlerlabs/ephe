/**
 * IntersectionObserver wiring: the hook observes the attached element with the
 * given threshold, reports intersections, and disconnects on unmount. jsdom has
 * no IntersectionObserver, so the class is stubbed and driven by hand.
 */
import { render, screen, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useInView } from './useInView'

type Entry = { isIntersecting: boolean }
type Cb = (entries: Entry[]) => void
type Inst = {
  cb: Cb
  observe: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
  threshold: number
}

let instances: Inst[] = []
const first = (): Inst => instances[0]!

function Probe({ threshold }: { threshold?: number }) {
  const { ref, isInView } = useInView(threshold)
  return <div ref={ref} data-testid="probe" data-inview={isInView ? 'yes' : 'no'} />
}

describe('useInView', () => {
  beforeEach(() => {
    instances = []
    class IO {
      observe = vi.fn()
      disconnect = vi.fn()
      constructor(cb: Cb, opts?: { threshold?: number }) {
        instances.push({
          cb,
          observe: this.observe,
          disconnect: this.disconnect,
          threshold: opts?.threshold ?? 0,
        })
      }
    }
    vi.stubGlobal('IntersectionObserver', IO)
  })

  afterEach(() => vi.unstubAllGlobals())

  it('starts out of view and observes the element with the default threshold', () => {
    render(<Probe />)
    expect(screen.getByTestId('probe')).toHaveAttribute('data-inview', 'no')
    expect(instances).toHaveLength(1)
    expect(first().observe).toHaveBeenCalledTimes(1)
    expect(first().threshold).toBe(0.1)
  })

  it('reports intersections both ways', () => {
    render(<Probe threshold={0.5} />)
    expect(first().threshold).toBe(0.5)
    act(() => first().cb([{ isIntersecting: true }]))
    expect(screen.getByTestId('probe')).toHaveAttribute('data-inview', 'yes')
    act(() => first().cb([{ isIntersecting: false }]))
    expect(screen.getByTestId('probe')).toHaveAttribute('data-inview', 'no')
  })

  it('disconnects on unmount', () => {
    const { unmount } = render(<Probe threshold={0.25} />)
    expect(first().threshold).toBe(0.25)
    unmount()
    expect(first().disconnect).toHaveBeenCalled()
  })
})
