/**
 * The About register names the licence the running version is released under.
 *
 * The product moved to the Business Source License 1.1, which is source-available and
 * not an open-source licence: a reader of the register has to be able to find that out
 * without opening the repository. The row carries the identifier as its value, the label
 * from the locale, and it sits directly under the version row it applies to.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { renderAbout } from './model/sections-misc'

const model = {
  about: {
    version: '0.0.1',
    active_provider: 'ollama',
    active_model: 'gemma4:12b',
    offline_capable: true,
  },
  // The stub returns the key, so a value that came from a locale leaf would fail below.
  t: (k: string) => k,
} as never

afterEach(cleanup)

describe('the About register states the licence', () => {
  it('carries the identifier as a literal value, not a translated word', () => {
    render(renderAbout(model))
    expect(screen.getByText('BUSL-1.1')).toBeTruthy()
  })

  it('labels the row from the locale', () => {
    render(renderAbout(model))
    expect(screen.getByText('settings.aboutLicense')).toBeTruthy()
  })

  it('sits directly under the version row it applies to', () => {
    render(renderAbout(model))
    const versionRow = screen.getByText('settings.aboutVersion').parentElement
    expect(versionRow?.nextElementSibling?.textContent).toBe('settings.aboutLicenseBUSL-1.1')
  })
})
