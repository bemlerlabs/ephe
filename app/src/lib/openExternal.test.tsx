/**
 * W-5 — the one way a page inside Ephe reaches a page outside it.
 *
 * Measured 2026-11-02 in the desktop shell: the marketplace detail sheet showed the
 * publisher's documentation as an underlined address and a click did nothing. Eleven anchors
 * across the marketplace, the setup page and the update dialog were plain blank-target links,
 * and a blank-target request has no window to open inside the shell — which is why the command
 * palette and the tray already detour through `browser_open_external`.
 *
 * The answer is a delegate at the entry, not a component per link: the twelfth link would
 * otherwise be found by a reader, and a shared component joined the eager `ui` chunk (15.09 kB
 * measured at its row, 17.16 kB with the door in it). What is held here is exactly the promise
 * the delegate makes — a plain left click on a foreign address leaves through the operating
 * system, a modified click stays the reader's, the app's own origin is not a way out, a surface
 * that already claimed the click keeps its answer, and a browser tab is untouched.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { installExternalLinks } from '@/lib/openExternal'

const invoke = vi.fn(async () => undefined)

const tauri = (value: unknown) => {
  Object.defineProperty(window, '__TAURI__', { value, configurable: true, writable: true })
}

function anchor(href: string, target = '_blank') {
  render(
    <a href={href} target={target} rel="noreferrer noopener">
      the address
    </a>,
  )
  return screen.getByRole('link')
}

describe('a blank-target link clicked in the desktop shell', () => {
  beforeAll(() => {
    tauri({ core: { invoke }, event: { listen: async () => () => undefined } })
    installExternalLinks()
  })

  beforeEach(() => invoke.mockClear())

  it('leaves through the operating system instead of the dead default', () => {
    const link = anchor('https://github.com/github/github-mcp-server')
    const handled = fireEvent.click(link)
    expect(handled, 'the click was prevented').toBe(false)
    expect(invoke).toHaveBeenCalledWith('browser_open_external', {
      url: 'https://github.com/github/github-mcp-server',
    })
  })

  it('leaves a modified click to the reader', () => {
    fireEvent.click(anchor('https://ephe.app/docs'), { ctrlKey: true })
    expect(invoke).not.toHaveBeenCalled()
  })

  it('is not a way out for the app itself', () => {
    fireEvent.click(anchor(`${window.location.origin}/#/settings`))
    expect(invoke).not.toHaveBeenCalled()
  })

  it('ignores a link that never asked for a new window', () => {
    fireEvent.click(anchor('https://ollama.com/download', '_self'))
    expect(invoke).not.toHaveBeenCalled()
  })

  it('lets a surface that already handled the click keep its answer', () => {
    render(
      <a href="https://opencode.ai/zen" target="_blank" onClick={(event) => event.preventDefault()}>
        claimed
      </a>,
    )
    fireEvent.click(screen.getByRole('link'))
    expect(invoke).not.toHaveBeenCalled()
  })
})

describe('the same link in a browser tab', () => {
  beforeAll(() => {
    tauri(undefined)
    invoke.mockClear()
  })

  it('is untouched — the anchor opens its own new tab', () => {
    const link = anchor('https://github.com/github/github-mcp-server')
    expect(fireEvent.click(link)).toBe(true)
    expect(invoke).not.toHaveBeenCalled()
  })
})
