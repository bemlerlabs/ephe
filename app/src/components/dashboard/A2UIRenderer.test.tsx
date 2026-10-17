/**
 * P1-2 — surfaces nest: a container owns the children it names.
 *
 * A surface is an adjacency list (a node lists its children by id). Before this
 * file, `Node` built empty fragments for those ids and `walk` appended the real
 * children beside the node, so a Card with children rendered as an empty box.
 * The nesting assertions below fail against that shape.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import A2UIRenderer, { parseA2UI } from '@/components/dashboard/A2UIRenderer'

const CARD = {
  surfaceId: 'demo',
  root: 'card1',
  components: [
    { id: 'card1', component: 'Card', label: 'Status', children: ['row1'] },
    { id: 'row1', component: 'Row', children: ['note', 'run'] },
    { id: 'note', component: 'Text', text: 'All green' },
    { id: 'run', component: 'Button', label: 'Run' },
  ],
}

const DEEP = {
  root: 'col',
  components: [
    { id: 'col', component: 'Column', children: ['outer'] },
    { id: 'outer', component: 'Card', label: 'Outer', children: ['inner'] },
    { id: 'inner', component: 'Card', label: 'Inner', children: ['leaf'] },
    { id: 'leaf', component: 'Text', text: 'Grandchild' },
  ],
}

const buttonSurface = (action?: unknown) => ({
  root: 'b',
  components: [{ id: 'b', component: 'Button', label: 'Run', ...(action ? { action } : {}) }],
})

const renderJSON = (surface: unknown, onAction?: (a: { name: string }) => void) =>
  render(<A2UIRenderer json={JSON.stringify(surface)} onAction={onAction} />)

describe('P1-2 — a container owns the children it names', () => {
  it('renders a Text child inside the Card element, not beside it', () => {
    renderJSON(CARD)
    const card = screen.getByText('Status').parentElement
    expect(card).toBeTruthy()
    expect(card).toContainElement(screen.getByText('All green'))
  })

  it('nests a Button child in the same card through its Row', () => {
    renderJSON(CARD)
    const card = screen.getByText('Status').parentElement
    expect(card).toContainElement(screen.getByText('Run'))
  })

  it('keeps nesting at every depth (Column > Card > Card > Text)', () => {
    renderJSON(DEEP)
    expect(screen.getByText('Outer').parentElement).toContainElement(screen.getByText('Inner'))
    expect(screen.getByText('Inner').parentElement).toContainElement(screen.getByText('Grandchild'))
  })

  it('renders every child exactly once', () => {
    renderJSON(CARD)
    expect(screen.getAllByText('All green')).toHaveLength(1)
    expect(screen.getAllByText('Status')).toHaveLength(1)
  })

  it('terminates on a node that names itself as its own child', () => {
    renderJSON({
      root: 'a',
      components: [
        { id: 'a', component: 'Column', children: ['a', 't'] },
        { id: 't', component: 'Text', text: 'reachable' },
      ],
    })
    expect(screen.getByTestId('a2ui-root')).toBeTruthy()
    expect(screen.getAllByText('reachable')).toHaveLength(1)
  })
})

describe('P1-2 — the Button contract is honest', () => {
  it('renders a Button without a channel as non-interactive, with no button role', () => {
    const { container } = renderJSON(CARD)
    expect(screen.queryByRole('button')).toBeNull()
    const chip = container.querySelector('[data-a2ui-inert="button"]')
    expect(chip).toBeTruthy()
    expect(chip!.textContent).toBe('Run')
  })

  it('keeps the inert chip free of the brand fill that reads as clickable', () => {
    const { container } = renderJSON(CARD)
    const chip = container.querySelector('[data-a2ui-inert="button"]')
    expect(String(chip!.className)).not.toContain('bg-brand')
  })

  it('fires the declared action through the channel the caller hands in', () => {
    const onAction = vi.fn()
    renderJSON(buttonSurface({ name: 'run_demo', payload: { step: 7 } }), onAction)
    const btn = screen.getByRole('button', { name: 'Run' })
    expect(btn.tagName).toBe('BUTTON')
    fireEvent.click(btn)
    expect(onAction).toHaveBeenCalledTimes(1)
    expect(onAction).toHaveBeenCalledWith({ name: 'run_demo', payload: { step: 7 } })
  })

  it('accepts a bare action name as the contract', () => {
    const onAction = vi.fn()
    renderJSON(buttonSurface('run_demo'), onAction)
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    expect(onAction).toHaveBeenCalledWith({ name: 'run_demo' })
  })

  it('does not invent an action for a Button the surface left bare', () => {
    const onAction = vi.fn()
    const { container } = renderJSON(buttonSurface(), onAction)
    expect(screen.queryByRole('button')).toBeNull()
    expect(container.querySelector('[data-a2ui-inert="button"]')).toBeTruthy()
    expect(onAction).not.toHaveBeenCalled()
  })
})

describe('P1-2 — parseA2UI rejects what cannot be a surface', () => {
  it('returns null for malformed JSON', () => {
    expect(parseA2UI('{ "components": [')).toBeNull()
  })

  it('returns null for JSON that declares no node at all', () => {
    expect(parseA2UI('{"hello":"world"}')).toBeNull()
  })

  it('returns null for an empty components list (an empty box is not a surface)', () => {
    expect(parseA2UI('{"components":[]}')).toBeNull()
  })

  it('accepts the id-map form and renders its root', () => {
    const map = { root: 'r', r: { id: 'r', component: 'Text', text: 'mapped' } }
    expect(parseA2UI(JSON.stringify(map))).toBeTruthy()
    renderJSON(map)
    expect(screen.getByText('mapped')).toBeTruthy()
  })
})
