/**
 * SEC-A: a refusal the pane can show.
 *
 * `browser.rs` answers both of its doors with a code and a `browser:refused` event;
 * `useNativeBrowserPane.ts` turns that into state. None of it is a deliverable until a
 * reader sees which address stayed out and why — the defect this replaces is a link that
 * cancels silently, which reads as a broken button rather than as a decision Ephe made.
 *
 * The copy is read from `locales/en.json` while the test runs, so a row that renders but
 * has no key behind it cannot pass here.
 */
import { describe, it, expect, vi } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { PreviewFrame } from './previewFrame'
import type { BrowserRefusal } from '@/lib/nativeBrowser'

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/en.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}
const EN = JSON.parse(readFileSync(resolve(findSrc(), 'locales/en.json'), 'utf8')) as {
  agentPanel: Record<string, string>
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const leaf = key.split('.')[1] ?? ''
      const template = EN.agentPanel[leaf] ?? (options?.defaultValue as string) ?? key
      return template.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(options?.[name] ?? ''))
    },
  }),
}))

function frame(refusal: BrowserRefusal | null) {
  const regionRef = { current: null as HTMLDivElement | null }
  return render(
    <PreviewFrame
      url="https://example.com/"
      nonce={1}
      preview={null}
      native
      nativeTitle="Example"
      nativeError={null}
      nativeRefusal={refusal}
      phase="ready"
      slow={false}
      contrast={false}
      narrow={false}
      proxyHtml={null}
      reading={false}
      regionRef={regionRef}
      onReload={() => {}}
      onFrameReady={() => {}}
    />,
  )
}

describe('the browser pane names the address it refused', () => {
  it('says which scheme it would not take, with the address itself', () => {
    frame({ url: 'file:///etc/hosts', scheme: 'file', reason: 'scheme-not-allowed' })
    const row = screen.getByTestId('preview-frame-refused')
    expect(row.textContent).toContain('file:///etc/hosts')
    expect(row.textContent).toContain('file:')
    expect(row.dataset.state).toBe('refused')
  })

  it('gives an address that belongs to Ephe a sentence of its own', () => {
    const { unmount } = frame({
      url: 'http://ipc.localhost/x',
      scheme: 'http',
      reason: 'app-own-origin',
    })
    const own = screen.getByTestId('preview-frame-refused').textContent ?? ''
    unmount()
    frame({ url: 'file:///etc/hosts', scheme: 'file', reason: 'scheme-not-allowed' })
    const foreign = screen.getByTestId('preview-frame-refused').textContent ?? ''
    expect(own).toContain('http://ipc.localhost/x')
    expect(own).not.toBe(foreign)
  })

  it('holds no offer to open the refused address somewhere else', () => {
    frame({ url: 'file:///etc/hosts', scheme: 'file', reason: 'scheme-not-allowed' })
    // The toolbar's own "open externally" belongs to the frame row below, and a refusal
    // must not hand the same address to the operating system.
    expect(screen.queryByTestId('preview-frame-refused')?.textContent).not.toMatch(/open/i)
  })

  it('stays out of the way while nothing was refused', () => {
    frame(null)
    expect(screen.queryByTestId('preview-frame-refused')).toBeNull()
  })

  /** The load row below describes the page that is showing; a refusal is its own state. */
  it('keeps the refusal and the load state as two rows', () => {
    frame({ url: 'file:///etc/hosts', scheme: 'file', reason: 'scheme-not-allowed' })
    expect(screen.queryByTestId('preview-frame-status')).toBeNull()
    expect(screen.getByTestId('preview-frame-refused')).toBeTruthy()
  })
})
