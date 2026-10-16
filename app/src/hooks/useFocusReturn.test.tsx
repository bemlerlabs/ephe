/**
 * Wave 10 (persona 06) — the focus contract of an ephemeral surface.
 *
 * The walkthrough spec `e2e/walkthrough/persona-06-tastatur.spec.ts` measures the
 * whole thing live (real Chromium, real Tab). These tests pin the same contract
 * where it is cheapest to read: the palette/rail declare `aria-modal` and never
 * kept Tab inside, never made the shell inert, and a close with a gone invoker
 * dropped focus onto `<body>`. Each case below fails if one of those four rules
 * is dropped again.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { useRef, useState } from 'react'
import {
  makeBackgroundInert,
  stableFocusTarget,
  tabStops,
  useFocusReturn,
  type FocusReturnApi,
} from './useFocusReturn'

beforeEach(() => {
  document.body.innerHTML = ''
})

const el = (tag: string, attrs: Record<string, string> = {}): HTMLElement => {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  return node
}

/** A minimal aria-modal surface driven by the hook. */
function Surface({ open }: { open: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const { onKeyDown } = useFocusReturn({ active: open, containerRef: ref })
  if (!open) return null
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      data-testid="surface"
      onKeyDown={onKeyDown}
    >
      <button data-testid="first">first</button>
      <button data-testid="last">last</button>
    </div>
  )
}

/** Opens/closes the surface and keeps the hook's API reachable. */
const apiRef: { current: FocusReturnApi | null } = { current: null }

function Host({ invoker = true }: { invoker?: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const api = useFocusReturn({ active: open, containerRef: ref })
  apiRef.current = api
  return (
    <div>
      <input id="ephe-chat-input" aria-label="composer" />
      {invoker && (
        <button data-testid="invoker" onClick={() => setOpen(true)}>
          invoker
        </button>
      )}
      <button data-testid="open" onClick={() => setOpen(true)}>
        open
      </button>
      <button
        data-testid="close"
        onClick={() => {
          // What every closing path in the product does: hand focus back in the
          // same task, before the surface unmounts.
          api.releaseFocus()
          setOpen(false)
        }}
      >
        close
      </button>
      {open && (
        <div
          ref={ref}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          data-testid="surface"
          onKeyDown={api.onKeyDown}
        >
          <button data-testid="first">first</button>
          <button data-testid="last">last</button>
        </div>
      )}
    </div>
  )
}

describe('useFocusReturn — (b) Tab stays inside while modal', () => {
  it('wraps forward from the last stop to the first and back with Shift+Tab', () => {
    render(<Surface open />)
    const first = screen.getByTestId('first')
    const last = screen.getByTestId('last')

    // fireEvent reports false when the handler called preventDefault.
    last.focus()
    expect(fireEvent.keyDown(last, { key: 'Tab' })).toBe(false)
    expect(document.activeElement).toBe(first)

    expect(fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })).toBe(false)
    expect(document.activeElement).toBe(last)
  })

  it('leaves Tab in the middle of the surface to the browser (no swallowed step)', () => {
    render(<Surface open />)
    expect(fireEvent.keyDown(screen.getByTestId('first'), { key: 'Tab' })).toBe(true)
  })

  it('counts exactly the Tab stops the walkthrough spec counts', () => {
    const container = el('div')
    const disabled = el('button', { disabled: '' })
    container.append(
      el('button'),
      el('input'),
      el('a', { href: '#x' }),
      disabled,
      el('span', { tabindex: '-1' }),
      el('div', { tabindex: '0' }),
    )
    expect(tabStops(container)).toEqual([
      container.children[0],
      container.children[1],
      container.children[2],
      container.children[5],
    ])
  })
})

describe('useFocusReturn — (a)+(c) focus in, shell inert, released on close', () => {
  it('moves focus into the surface and makes the shell behind it inert', () => {
    render(<Host />)
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.click(invoker)

    expect(document.activeElement).toBe(screen.getByTestId('first'))
    expect(invoker.hasAttribute('inert')).toBe(true)
    expect(invoker.getAttribute('aria-hidden')).toBe('true')
  })

  it('lifts the inert again and hands focus back to the invoker on close', () => {
    render(<Host />)
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.click(invoker)
    fireEvent.click(screen.getByTestId('close'))

    expect(invoker.hasAttribute('inert')).toBe(false)
    expect(invoker.getAttribute('aria-hidden')).toBeNull()
    expect(document.activeElement).toBe(invoker)
  })
})

describe('useFocusReturn — (d) never <body>', () => {
  it('a close with no invoker at all lands on the stable target', () => {
    // The palette case from the walkthrough: nothing was focused when the
    // surface opened, so there is no invoker to go back to.
    render(<Host />)
    fireEvent.click(screen.getByTestId('open'))
    expect(document.activeElement).toBe(screen.getByTestId('first'))

    fireEvent.click(screen.getByTestId('close'))

    expect(document.activeElement).toBe(document.getElementById('ephe-chat-input'))
    expect(document.activeElement).not.toBe(document.body)
  })

  it('hands focus back in the same task, before the surface unmounts', () => {
    // The palette-opened-settings case: the next modal opens in the task that
    // closes this one, so the handback must not wait for an effect — by then the
    // surface has unmounted and focus would end up on <body>.
    render(<Host />)
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.click(invoker)

    act(() => apiRef.current?.releaseFocus())
    expect(document.activeElement).toBe(invoker)
  })

  it('never resolves to <body> — no usable target is the honest answer', () => {
    document.body.append(el('div', { id: 'random' }))
    expect(stableFocusTarget()).toBeNull()
  })

  it('prefers the app shell targets the walkthrough names', () => {
    const main = el('main', { id: 'main-content', tabindex: '-1' })
    document.body.append(main)
    expect(stableFocusTarget()).toBe(main)

    const composer = el('input', { id: 'ephe-chat-input' })
    document.body.append(composer)
    expect(stableFocusTarget()).toBe(composer)
  })

  it('skips a stable target another modal has made inert', () => {
    document.body.append(el('main', { id: 'main-content', tabindex: '-1', inert: '' }))
    expect(stableFocusTarget()).toBeNull()
  })
})

describe('makeBackgroundInert', () => {
  it('unreaches the siblings along the ancestor chain and nothing else', () => {
    const sidebar = el('nav', { id: 'sidebar' })
    const main = el('main', { id: 'main' })
    const surface = el('div')
    document.body.append(sidebar, main, surface)

    const release = makeBackgroundInert(surface)

    expect(sidebar.hasAttribute('inert')).toBe(true)
    expect(main.getAttribute('aria-hidden')).toBe('true')
    expect(surface.hasAttribute('inert')).toBe(false)

    release()
    expect(sidebar.hasAttribute('inert')).toBe(false)
    expect(main.getAttribute('aria-hidden')).toBeNull()
  })

  it('leaves a subtree another surface already made inert alone — and does not release it', () => {
    const own = el('div', { inert: '' })
    const surface = el('div')
    document.body.append(own, surface)

    const release = makeBackgroundInert(surface)
    expect(own.hasAttribute('inert')).toBe(true)

    release()
    // Still the other surface's call — this one must not unlock it.
    expect(own.hasAttribute('inert')).toBe(true)
  })
})
