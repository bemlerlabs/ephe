/**
 * The installed PWA under the notch.
 *
 * `app/index.html` sets `viewport-fit=cover` and a `black-translucent` status bar,
 * so an installed iOS web view runs the full height of the screen and the system
 * draws the clock (top) and the home indicator (bottom) *over* the page. Every
 * band the user needs at an edge therefore has to clear that edge itself — which
 * is what `env(safe-area-inset-*)` is for. Until this landed, the shell used it
 * nowhere: the chat header's menu button sat under the clock and the bottom band
 * under the home indicator, while `settings/index.tsx` and `ui/Toaster.tsx`
 * already carried the bottom inset.
 *
 * jsdom and headless Chromium both compute `env(safe-area-inset-*)` as 0, so the
 * pixel value resolves only on a device with a notch. What is held here is the
 * contract, not the measurement: the class is asserted on the *rendered* bottom
 * band, and scanned from the shell's source line for the chat header, which is
 * inline JSX in a 771-line component that has no standalone render. A green run
 * proves a later edit cannot silently drop the inset; the 34 px itself is an
 * install-on-a-phone measurement, and is not claimed here.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    // t returns the key; the assertions below read markup.
    useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
  }
})
vi.mock('@/lib/api', () => ({
  getContextBudget: vi.fn(async () => null),
  getTasks: vi.fn(async () => []),
}))
vi.mock('@/lib/api/misc', () => ({ gitStatus: vi.fn(async () => null) }))

// Not `new URL('./chat/index.tsx', import.meta.url)`: Vite rewrites that shape
// into a built-asset URL and the read then fails on the scheme (the reason
// `settings/registerMobileStrip.test.tsx` reads its source the same way).
const CHAT_SHELL = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'chat', 'index.tsx'),
  'utf8',
)

/** The one source line holding `anchor`; a missing or doubled anchor fails naming it. */
function line(anchor: string): string {
  const hits = CHAT_SHELL.split('\n').filter((l) => l.includes(anchor))
  const [only] = hits
  if (only === undefined || hits.length !== 1) {
    throw new Error(`"${anchor}" must sit on exactly one source line, found ${hits.length}`)
  }
  return only
}

describe('safe-area insets on the chat shell', () => {
  it('clears the home indicator on the bottom-most surface of the column', () => {
    render(<StatusBar messages={[]} windowTokens={8192} />)
    const cls = String(screen.getByTestId('status-bar').className)
    expect(cls).toMatch(/pb-\[calc\([^\]]*env\(safe-area-inset-bottom\)\)\]/)
    // The band is the column's last child, so the inset belongs here and not on
    // the composer one row above it.
    expect(cls).toMatch(/flex-shrink-0/)
  })

  it('clears the status bar on the chat header', () => {
    const header = line('relative z-sticky border-b border-hairline px-4')
    expect(header).toMatch(/pt-\[calc\([^\]]*env\(safe-area-inset-top\)\)\]/)
  })

  it('reserves the Windows caption corner on the same header', () => {
    // I2: the 138 px right inset was written to the root and read by nobody.
    const header = CHAT_SHELL.split('\n').find((l) => l.includes('md:pr-[calc(1rem+var(--chrome-inset-right'))
    expect(header).toBeTruthy()
    expect(header).toContain('isTauri')
  })

  it('clears it on the mobile drawer header too — the phone reaches the app through it', () => {
    const sidebar = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'Sidebar.tsx'),
      'utf8',
    )
    expect(sidebar).toMatch(/pt-\[calc\([^\]]*env\(safe-area-inset-top\)\)\]/)
  })
})
