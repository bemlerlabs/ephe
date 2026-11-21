import { useState } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DeepSection } from '@/types'
import type { TabKey } from '../types'
import { useInstantAppearance } from './useInstantAppearance'

const SECTIONS: DeepSection[] = [
  {
    key: 'appearance',
    fields: [
      {
        key: 'appearance.font_scale',
        type: 'number',
        label: 'Font scale',
        labelEn: 'Font scale',
        default: 100,
        value: 100,
        min: 80,
        max: 150,
      },
      {
        key: 'appearance.animations_enabled',
        type: 'bool',
        label: 'Animations',
        labelEn: 'Animations',
        default: true,
        value: true,
      },
    ],
  },
]

const INITIAL = {
  appearance: {
    'appearance.font_scale': 100,
    'appearance.animations_enabled': true,
  },
} satisfies Record<string, Record<string, string | number | boolean>>

function setup(initialTab: TabKey = 'appearance') {
  const save = vi.fn<(scope?: string[]) => Promise<{ ok: boolean; detail?: string }>>(async () => ({
    ok: true,
  }))
  const view = renderHook(
    ({ activeTab }: { activeTab: TabKey }) => {
      const [draft, setDraft] =
        useState<Record<string, Record<string, string | number | boolean>>>(INITIAL)
      const instant = useInstantAppearance({
        isOpen: true,
        activeTab,
        deepDraft: draft,
        deepSections: SECTIONS,
        setDeepDraft: setDraft,
        saveDeepSettings: save,
      })
      return { draft, setDraft, ...instant }
    },
    { initialProps: { activeTab: initialTab } },
  )
  return { ...view, save }
}

const setFont = (view: ReturnType<typeof setup>, value: number) =>
  act(() => {
    view.result.current.setDraft((draft) => ({
      ...draft,
      appearance: { ...draft.appearance, 'appearance.font_scale': value },
    }))
  })

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('instant appearance', () => {
  it('persists once after the debounce', async () => {
    const view = setup()
    setFont(view, 120)
    expect(view.save).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(499)
    })
    expect(view.save).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(view.save).toHaveBeenCalledTimes(1)
    expect(view.save).toHaveBeenCalledWith(['appearance'])
  })

  it('coalesces rapid edits into one write', async () => {
    const view = setup()
    setFont(view, 110)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })
    setFont(view, 120)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })
    setFont(view, 130)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    expect(view.save).toHaveBeenCalledTimes(1)
  })

  it('rolls back to the last persisted value when the write fails', async () => {
    const view = setup()
    view.save.mockResolvedValueOnce({ ok: false, detail: '500' })
    setFont(view, 140)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    expect(view.result.current.draft.appearance?.['appearance.font_scale']).toBe(100)
    expect(view.result.current.instantStatus).toBe('error')
    expect(view.result.current.instantError).toBe('500')
  })

  it('flushes a pending write on a tab switch', async () => {
    const view = setup()
    setFont(view, 125)
    await act(async () => {
      view.rerender({ activeTab: 'engine' })
    })
    expect(view.save).toHaveBeenCalledTimes(1)
  })

  it('flushes a pending write on unmount', async () => {
    const view = setup()
    setFont(view, 125)
    await act(async () => {
      view.unmount()
    })
    expect(view.save).toHaveBeenCalledTimes(1)
  })
})
