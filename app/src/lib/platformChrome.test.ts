import { beforeEach, describe, expect, it, vi } from 'vitest'

const desk = vi.hoisted(() => ({ value: false }))
vi.mock('@/lib/tauriBridge', () => ({ isDesktopShell: () => desk.value }))

import { applyPlatformChrome, resolvePlatformChromeSpec } from './platformChrome'

beforeEach(() => {
  desk.value = false
  document.documentElement.style.removeProperty('--chrome-inset-left')
  document.documentElement.style.removeProperty('--chrome-inset-right')
})

describe('the platform chrome spec (I1/I2)', () => {
  it('gives the macOS shell 76 px for the window buttons', () => {
    expect(resolvePlatformChromeSpec('darwin', true)).toEqual({ insetLeft: 76, insetRight: 0 })
  })

  it('gives the Windows shell 138 px on the right', () => {
    expect(resolvePlatformChromeSpec('win32', true)).toEqual({ insetLeft: 0, insetRight: 138 })
  })

  it('reserves nothing in a browser, whatever the platform', () => {
    expect(resolvePlatformChromeSpec('darwin', false)).toEqual({ insetLeft: 0, insetRight: 0 })
    expect(resolvePlatformChromeSpec('win32', false)).toEqual({ insetLeft: 0, insetRight: 0 })
  })

  it('reserves nothing on a desktop Linux build', () => {
    expect(resolvePlatformChromeSpec('linux', true)).toEqual({ insetLeft: 0, insetRight: 0 })
  })

  it('writes both insets onto the root element', () => {
    desk.value = true
    applyPlatformChrome('darwin')
    expect(document.documentElement.style.getPropertyValue('--chrome-inset-left')).toBe('76px')
    expect(document.documentElement.style.getPropertyValue('--chrome-inset-right')).toBe('0px')
    applyPlatformChrome('win32')
    expect(document.documentElement.style.getPropertyValue('--chrome-inset-left')).toBe('0px')
    expect(document.documentElement.style.getPropertyValue('--chrome-inset-right')).toBe('138px')
  })
})
