// R24: TelegramPairingCard — token setup, QR pairing flow, devices + revoke.
// All API calls mocked (no backend, no network).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { TelegramPairingCard } from './TelegramPairingCard'
import type { TelegramDevice, TelegramStatus } from '@/lib/api'

const api = vi.hoisted(() => ({
  getTelegramStatus: vi.fn(),
  saveTelegramToken: vi.fn(),
  deleteTelegramToken: vi.fn(),
  startTelegramChannel: vi.fn(),
  stopTelegramChannel: vi.fn(),
  createTelegramPairing: vi.fn(),
  listTelegramDevices: vi.fn(),
  revokeTelegramDevice: vi.fn(),
}))

vi.mock('@/lib/api', () => api)

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        k === 'settings.telegramExpiresIn' && opts ? `Valid for ${opts.seconds} s` : k,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const STATUS_NO_TOKEN: TelegramStatus = {
  token_configured: false,
  token_masked: null,
  running: false,
  bot_username: null,
  paired_count: 0,
  session_count: 0,
  last_error: null,
}

const STATUS_WITH_TOKEN: TelegramStatus = {
  ...STATUS_NO_TOKEN,
  token_configured: true,
  token_masked: '…abcd (47 chars)',
  bot_username: 'ephe_bot',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getTelegramStatus.mockResolvedValue(STATUS_NO_TOKEN)
  api.listTelegramDevices.mockResolvedValue([] as TelegramDevice[])
})

describe('TelegramPairingCard', () => {
  it('shows one-time token setup when no token is configured', async () => {
    render(<TelegramPairingCard />)
    expect(await screen.findByTestId('telegram-setup')).toBeInTheDocument()
    expect(screen.getByTestId('telegram-token-input')).toBeInTheDocument()
  })

  it('saves the bot token and refreshes status', async () => {
    api.saveTelegramToken.mockResolvedValue({ mode: 'file_0600', masked: '…abcd' })
    render(<TelegramPairingCard />)
    const input = await screen.findByTestId('telegram-token-input')
    fireEvent.change(input, { target: { value: '123456789:AAF3xExampleTokenValue000000' } })
    fireEvent.click(screen.getByTestId('telegram-token-save'))

    await waitFor(() => {
      expect(api.saveTelegramToken).toHaveBeenCalledWith('123456789:AAF3xExampleTokenValue000000')
    })
  })

  it('surfaces API errors in the failure row', async () => {
    api.getTelegramStatus.mockRejectedValue(new Error('API 503: backend down'))
    render(<TelegramPairingCard />)
    expect(await screen.findByTestId('telegram-error')).toHaveTextContent('backend down')
  })

  it('renders QR pairing flow with deep link and countdown', async () => {
    api.getTelegramStatus.mockResolvedValue(STATUS_WITH_TOKEN)
    api.createTelegramPairing.mockResolvedValue({
      deep_link: 'https://t.me/ephe_bot?start=T0K3N',
      qr_base64: 'QUJD',
      issued_at: Date.now() / 1000,
      expires_at: Date.now() / 1000 + 600,
      ttl_seconds: 600,
    })
    render(<TelegramPairingCard />)
    fireEvent.click(await screen.findByTestId('telegram-pair-button'))

    const qr = await screen.findByTestId('telegram-qr')
    expect(qr).toHaveAttribute('src', 'data:image/png;base64,QUJD')
    const link = screen.getByTestId('telegram-open-link')
    expect(link).toHaveAttribute('href', 'https://t.me/ephe_bot?start=T0K3N')
    expect(screen.getByTestId('telegram-qr-expiry')).toHaveTextContent('Valid for')
  })

  it('revoke requires a second click and then revokes the device', async () => {
    api.getTelegramStatus.mockResolvedValue(STATUS_WITH_TOKEN)
    api.listTelegramDevices.mockResolvedValue([
      { user_id: 42, label: 'Test User', paired_at: '2026-09-06T10:00:00Z' },
    ])
    api.revokeTelegramDevice.mockResolvedValue({ ok: true })
    render(<TelegramPairingCard />)

    const row = await screen.findByTestId('telegram-device-42')
    expect(row).toHaveTextContent('Test User')

    // First click: confirmation only (in the test t returns the i18n key)
    fireEvent.click(screen.getByTestId('telegram-revoke-42'))
    expect(screen.getByTestId('telegram-revoke-42')).toHaveTextContent(
      'settings.telegramRevokeConfirm',
    )
    expect(api.revokeTelegramDevice).not.toHaveBeenCalled()

    // Second click: revokes access
    fireEvent.click(screen.getByTestId('telegram-revoke-42'))
    await waitFor(() => expect(api.revokeTelegramDevice).toHaveBeenCalledWith(42))
  })

  it('toggles the polling runner', async () => {
    api.getTelegramStatus.mockResolvedValue({ ...STATUS_WITH_TOKEN, running: true })
    api.stopTelegramChannel.mockResolvedValue({ running: false })
    render(<TelegramPairingCard />)

    fireEvent.click(await screen.findByTestId('telegram-toggle-runner'))
    await waitFor(() => expect(api.stopTelegramChannel).toHaveBeenCalled())
  })
})
