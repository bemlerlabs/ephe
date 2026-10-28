import { isDesktopShell } from '@/lib/tauriBridge'

export interface PlatformChromeSpec {
  /** Room for the macOS window buttons, which sit over the top-left corner. */
  insetLeft: number
  /** Room for the Windows 11 caption buttons, which sit over the top-right corner. */
  insetRight: number
}

/**
 * I1/I2: how much of the top row the native window buttons own. The PWA and the
 * browser have no such buttons, so only the desktop shell reserves anything —
 * a page in a tab that padded itself would just look broken.
 */
export function resolvePlatformChromeSpec(platform: string, desktop: boolean): PlatformChromeSpec {
  if (!desktop) return { insetLeft: 0, insetRight: 0 }
  if (platform === 'darwin' || platform.startsWith('Mac')) return { insetLeft: 76, insetRight: 0 }
  if (platform === 'win32' || platform.startsWith('Win')) return { insetLeft: 0, insetRight: 138 }
  return { insetLeft: 0, insetRight: 0 }
}

/** The browser's own platform string, in the shape the resolver expects. */
export function currentPlatform(): string {
  if (typeof navigator === 'undefined') return 'other'
  const uaData = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData
  return uaData?.platform || navigator.platform || 'other'
}

/** Put the insets on the root as custom properties; idempotent, like the type scale. */
export function applyPlatformChrome(platform = currentPlatform()): PlatformChromeSpec {
  const spec = resolvePlatformChromeSpec(platform, isDesktopShell())
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--chrome-inset-left', `${spec.insetLeft}px`)
    document.documentElement.style.setProperty('--chrome-inset-right', `${spec.insetRight}px`)
  }
  return spec
}
