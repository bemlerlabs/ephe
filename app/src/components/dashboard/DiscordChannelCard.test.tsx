// W3d — Discord card in the mobile tab: 'not configured' status, token setup, runner toggle.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
  }),
}))

const getDiscordStatus = vi.fn(async (_a?: unknown) => ({
  configured: false,
  token_masked: null as string | null,
  running: false,
  last_error: null as string | null,
  message: 'not configured',
}))
const startDiscordChannel = vi.fn(async (_a?: unknown) => ({ running: true }))
const stopDiscordChannel = vi.fn(async (_a?: unknown) => ({ running: false }))
const saveDiscordToken = vi.fn(async (_a?: unknown) => ({
  mode: 'file_0600',
  masked: '…abcd (46 Zeichen)',
}))
vi.mock('@/lib/api', () => ({
  getDiscordStatus: (...a: unknown[]) => getDiscordStatus(...(a as [unknown?])),
  saveDiscordToken: (...a: unknown[]) => saveDiscordToken(...(a as [unknown?])),
  deleteDiscordToken: vi.fn(async () => ({ ok: true })),
  startDiscordChannel: (...a: unknown[]) => startDiscordChannel(...(a as [unknown?])),
  stopDiscordChannel: (...a: unknown[]) => stopDiscordChannel(...(a as [unknown?])),
}))

import { DiscordChannelCard } from './DiscordChannelCard'

beforeEach(() => localStorage.clear())

describe('DiscordChannelCard (W3d)', () => {
  it('ohne Token: Karten-Rumpf mit Setup-Block und Status-Pille', async () => {
    render(<DiscordChannelCard />)
    expect(await screen.findByTestId('discord-card')).toBeTruthy()
    expect(screen.getByTestId('discord-setup')).toBeTruthy()
    expect(screen.getByTestId('discord-token-input')).toBeTruthy()
    expect(screen.getByTestId('discord-status-dot')).toBeTruthy()
  })

  it('Token-Speichern ruft saveDiscordToken mit getipptem Wert', async () => {
    render(<DiscordChannelCard />)
    fireEvent.change(await screen.findByTestId('discord-token-input'), {
      target: { value: '1432891234567890123.abc.ABC' },
    })
    fireEvent.click(screen.getByTestId('discord-token-save'))
    await waitFor(() =>
      expect(saveDiscordToken).toHaveBeenCalledWith('1432891234567890123.abc.ABC'),
    )
  })

  it('Runner-Schalter ruft startDiscordChannel, wenn nicht laufend', async () => {
    getDiscordStatus.mockResolvedValue({
      configured: true,
      token_masked: '…abcd (46 Zeichen)',
      running: false,
      last_error: null,
      message: '',
    })
    render(<DiscordChannelCard />)
    const btn = await screen.findByTestId('discord-toggle-runner')
    fireEvent.click(btn)
    await waitFor(() => expect(startDiscordChannel).toHaveBeenCalled())
  })
})
