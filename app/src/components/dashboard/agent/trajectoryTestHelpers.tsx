import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TrajectoryTab } from './tabsA'

// jsdom reports height 0 — the virtualizer needs a measured scroll height
// (the established pattern from ChatLayout.focus.test.tsx).
export const patchHeight = (prop: 'offsetHeight' | 'clientHeight') => {
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    get() {
      return this.classList.contains('overflow-y-auto') ? 600 : 0
    },
  })
}

// The turn head links to the workbench (A3 run backwards) — so this view needs
// a Router.
export const renderTab = () =>
  render(
    <MemoryRouter>
      <TrajectoryTab />
    </MemoryRouter>,
  )
