/**
 * The host record is the shell's box. A page field has no key here.
 */
import { describe, expect, it } from 'vitest'
import { hostRecord, hostRecordKeys, type HostSurface } from './surfaceHost'

const record: HostSurface = {
  slot: 'overlay',
  x: 12.4,
  y: 8.2,
  width: 360.2,
  height: 240.8,
  open: true,
  minimized: false,
  placed: true,
}

describe('the host record', () => {
  it('rounds the box and carries only the host fields', () => {
    expect(hostRecord(record)).toEqual({
      slot: 'overlay',
      x: 12,
      y: 8,
      width: 360,
      height: 241,
      open: true,
      minimized: false,
      placed: true,
    })
    expect(hostRecordKeys(record).sort()).toEqual([
      'height',
      'minimized',
      'open',
      'placed',
      'slot',
      'width',
      'x',
      'y',
    ])
  })
})
