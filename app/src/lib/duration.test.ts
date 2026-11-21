import { describe, it, expect } from 'vitest'
import { formatDuration } from '@/lib/duration'
import { seedDeepSettings } from '@/lib/deepSettings'

describe('formatDuration ([F10] turn timer)', () => {
  it('below a minute: only seconds', () => {
    expect(formatDuration(0)).toBe('0s')
    expect(formatDuration(29_400)).toBe('29s')
    expect(formatDuration(59_999)).toBe('59s')
  })

  it('from a minute on: Xm Ys like the reference', () => {
    expect(formatDuration(60_000)).toBe('1m')
    expect(formatDuration(84_000)).toBe('1m 24s')
    expect(formatDuration(171_000)).toBe('2m 51s')
  })

  it('from the hour on: seconds drop away', () => {
    expect(formatDuration(3_600_000)).toBe('1h')
    expect(formatDuration(4_200_000)).toBe('1h 10m')
  })

  it('negative and absurd values clamp to 0', () => {
    expect(formatDuration(-5)).toBe('0s')
  })

  // I6-3: `chat.duration_format` is the only place the clock form appears.
  // Without a registry (backend unreachable) the terse default must stay.
  it('without the register the terse Ephe norm stays', () => {
    seedDeepSettings(null)
    expect(formatDuration(84_000)).toBe('1m 24s')
  })

  it('clock form: MM:SS, from the hour on H:MM:SS', () => {
    seedDeepSettings([
      {
        key: 'chat',
        fields: [
          {
            key: 'chat.duration_format',
            type: 'select',
            label: 'Dauer-Format',
            labelEn: 'Duration format',
            default: 'compact',
            value: 'clock',
          },
        ],
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any)
    expect(formatDuration(84_000)).toBe('01:24')
    expect(formatDuration(3_852_000)).toBe('1:04:12')
    expect(formatDuration(9_999)).toBe('00:09')
    seedDeepSettings(null)
  })
})
