// One layer question, pinned: the settings route is a sheet on the chrome step, and
// the plugin dock is portalled after the shell. That is what lets a surface opened
// from a plugin row show up over the page that owns the row — the store's "Open"
// action used to paint a window behind the settings page.
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

function srcFile(relative: string): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src', relative)
    if (existsSync(candidate)) return readFileSync(candidate, 'utf8')
  }
  throw new Error(`app/src/${relative} not found below ${process.cwd()}`)
}

describe('settings sheet layering', () => {
  it('sits on the overlay step, not on the modal step', () => {
    const sheet = srcFile('components/dashboard/settings/index.tsx')
    const page = sheet.slice(sheet.indexOf('data-testid="settings-page"'))
    const className = page.slice(
      page.indexOf('className='),
      page.indexOf('>', page.indexOf('className=')),
    )
    expect(className).toContain('z-overlay')
    expect(className).not.toContain('z-modal')
  })

  it('renders the plugin dock after the shell, so its windows paint above the sheet', () => {
    const app = srcFile('App.tsx')
    const shell = app.indexOf('<AppShell>')
    const dock = app.indexOf('<OverlayHost />')
    expect(shell).toBeGreaterThan(-1)
    expect(dock).toBeGreaterThan(shell)
  })

  it('gives the fixed dock host its own step above the sheet', () => {
    const css = srcFile('components/shell/OverlayHost.css')
    expect(css).toMatch(
      /\.overlay-host\s*\{[^}]*z-index:\s*calc\(var\(--z-index-overlay\)\s*\+\s*1\)/,
    )
  })

  it('keeps the overlay window on the overlay step under the modal step', () => {
    const css = srcFile('components/shell/OverlayHost.css')
    expect(css).toMatch(/z-index:\s*calc\(var\(--z-index-overlay\)\s*\+\s*var\(--stack-rank/)
  })
})
