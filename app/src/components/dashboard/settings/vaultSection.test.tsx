/** The vault area lists declared credentials and can forget one — never read one. */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const api = vi.hoisted(() => ({
  getMcpEnv: vi.fn(),
  getSecretStatus: vi.fn(),
  removeSecret: vi.fn(),
}))

vi.mock('@/lib/api', () => api)

import { VaultSection } from './model/sections-vault'

const model = { t: (key: string) => key } as never

beforeEach(() => {
  vi.clearAllMocks()
  api.getMcpEnv.mockResolvedValue({ servers: { 'stdio:npx -y web-search': ['WEB_SEARCH_KEY'] } })
  api.getSecretStatus.mockResolvedValue([
    { name: 'WEB_SEARCH_KEY', present: true, mode: 'keyring' },
  ])
  api.removeSecret.mockResolvedValue({ name: 'WEB_SEARCH_KEY', present: false, mode: '' })
})

describe('vault section', () => {
  it('lists a declared name with its storage mode', async () => {
    render(<VaultSection model={model} />)
    await waitFor(() => expect(screen.getByTestId('vault-name-WEB_SEARCH_KEY')).toBeTruthy())
    expect(screen.getByTestId('vault-name-WEB_SEARCH_KEY').textContent).toContain(
      'settings.vaultStored.keyring',
    )
    expect(screen.getByTestId('vault-spec-stdio:npx -y web-search')).toBeTruthy()
  })

  it('forgets a value through its own route', async () => {
    render(<VaultSection model={model} />)
    await waitFor(() => expect(screen.getByTestId('vault-forget-WEB_SEARCH_KEY')).toBeTruthy())
    fireEvent.click(screen.getByTestId('vault-forget-WEB_SEARCH_KEY'))
    await waitFor(() => expect(api.removeSecret).toHaveBeenCalledWith('WEB_SEARCH_KEY'))
    await waitFor(() =>
      expect(screen.getByTestId('vault-name-WEB_SEARCH_KEY').textContent).toContain(
        'settings.vaultMissing',
      ),
    )
  })

  it('says so when no connector asks for anything', async () => {
    api.getMcpEnv.mockResolvedValue({ servers: {} })
    render(<VaultSection model={model} />)
    await waitFor(() => expect(screen.getByTestId('vault-empty')).toBeTruthy())
  })
})
