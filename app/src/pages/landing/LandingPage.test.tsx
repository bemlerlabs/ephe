/**
 * The landing page is copy and links. The test resolves the real `en.json` through a
 * minimal `t`, so a missing key or an edited number fails here instead of shipping a raw
 * key path or a figure the studies do not carry.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async () => {
  const en = (await import('@/locales/en.json')).default as Record<string, unknown>
  const lookup = (key: string): unknown =>
    key
      .split('.')
      .reduce<unknown>(
        (node, part) =>
          node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
        en,
      )
  const t = (key: string, opts?: Record<string, unknown>) => {
    const value = lookup(key)
    if (typeof value !== 'string') throw new Error(`landing copy is missing: ${key}`)
    return value.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(opts?.[name] ?? ''))
  }
  return { useTranslation: () => ({ t }) }
})

import LandingPage from './LandingPage'
import { COMPARISON_ROWS, INSTALL_COMMAND } from '@/components/landing'

function renderPage() {
  return render(<LandingPage />)
}

beforeEach(() => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('the landing page', () => {
  it('opens with the one-sentence promise and a single h1', async () => {
    renderPage()

    expect(
      screen.getByRole('heading', { level: 1, name: 'One command. Your engine. Your machine.' }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('prints the measured figures the two studies report', async () => {
    renderPage()

    const proof = screen.getByTestId('landing-proof')
    expect(proof.textContent).toContain('28.6%')
    expect(proof.textContent).toContain('16.6%')
    expect(proof.textContent).toContain('124')
    expect(proof.textContent).toContain('10–15 pp')
    expect(proof.textContent).toContain('288 runs')
    const accounts = screen.getByTestId('landing-proof-accounts')
    expect(accounts.textContent?.startsWith('0')).toBe(true)
    expect(accounts.textContent).toContain('accounts and default models')
    expect(screen.getByRole('link', { name: /JAWs 2026/ })).toHaveAttribute(
      'href',
      'https://arxiv.org/abs/2601.20404',
    )
    expect(screen.getByRole('link', { name: /REALM 2026/ })).toHaveAttribute(
      'href',
      'https://aclanthology.org/2026.realm-1.5/',
    )
  })

  it('answers all six comparison rows and links the file that proves each one', async () => {
    renderPage()

    const table = screen.getByTestId('landing-comparison')
    for (const row of COMPARISON_ROWS) {
      const tr = screen.getByTestId(`landing-row-${row.id}`)
      expect(table).toContainElement(tr)
      expect(tr.textContent).toContain(row.proofPath)
      expect(tr.querySelector(`a[href$="${row.proofPath}"]`)).not.toBeNull()
    }
  })

  it('names the tools a visitor comes from, and the import path', async () => {
    renderPage()

    const page = screen.getByTestId('landing-page')
    // The public page never names another product (owner rule): the comparison asks the
    // question and answers it with Ephe's own proofs.
    expect(page.textContent).not.toMatch(/\b(Claude|Cursor|Hermes|OpenClaw|Qoder)\b/)
    expect(screen.getByTestId('landing-import-command').textContent).toBe(
      'ephe import ~/path-to-your-old-agent-setup',
    )
    expect(screen.getByTestId('landing-import-rows').textContent).toContain('~/.ephe/persona.md')
  })

  it('copies the installer line and says so', async () => {
    renderPage()

    expect(screen.getByTestId('landing-install-command').textContent).toBe(INSTALL_COMMAND)
    fireEvent.click(screen.getByTestId('landing-install-copy'))

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(INSTALL_COMMAND))
    await waitFor(() =>
      expect(screen.getByTestId('landing-install-status').textContent).toContain('copied'),
    )
  })

  it('reports a refused clipboard instead of leaving the click silent', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    })
    renderPage()

    fireEvent.click(screen.getByTestId('landing-install-copy'))

    await waitFor(() =>
      expect(screen.getByTestId('landing-install-status').textContent).toContain(
        'The clipboard refused',
      ),
    )
  })

  it('jumps to the install section without leaving the route', async () => {
    renderPage()

    expect(() => fireEvent.click(screen.getByTestId('landing-install-jump'))).not.toThrow()
    expect(window.location.hash).toBe('')
  })
})
