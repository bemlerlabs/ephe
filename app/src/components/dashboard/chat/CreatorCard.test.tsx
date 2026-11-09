/**
 * #28 — the creator card in the run log.
 *
 * Two promises are tested here. The card states only what a creator answer said, and the
 * one action it offers is the mount the platform already owns: the store view is read, and
 * whatever that layer answers — a surface, a refusal, nothing at all — is what the reader
 * sees.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import CreatorCard from './CreatorCard'

const apiMocks = vi.hoisted(() => ({ getPlugins: vi.fn() }))
const surfaceMocks = vi.hoisted(() => ({
  show: vi.fn(),
  isOpen: vi.fn(() => false),
  hide: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ getPlugins: apiMocks.getPlugins }))
vi.mock('@/lib/pluginDisplay', () => ({
  showPluginSurface: surfaceMocks.show,
  isPluginSurfaceOpen: surfaceMocks.isOpen,
  hidePluginSurface: surfaceMocks.hide,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && Object.keys(opts).length ? `${key}<${JSON.stringify(opts)}>` : key,
    i18n: { language: 'en' },
  }),
}))

const SCAFFOLD = JSON.stringify({
  bundle: '/tmp/creator/plugins/timer',
  name: 'timer',
  version: '0.1.0',
  license: 'LicenseRef-proprietary',
  publisher: 'Independent',
  files: ['ephe-plugin.json', 'ui/app.css', 'ui/app.js', 'ui/index.html'],
  next: 'write_plugin_source(bundle, path, content), then verify_plugin_bundle(bundle)',
})
const VERIFIED = JSON.stringify({
  ok: true,
  bundle: '/tmp/creator/plugins/timer',
  sha256: 'a'.repeat(64),
  name: 'timer',
  version: '0.1.0',
  tools: [],
  next: 'install_plugin_bundle(bundle)',
})
const INSTALLED = JSON.stringify({
  status: 'installed',
  name: 'timer',
  version: '0.1.0',
  trust: 'local',
  sha256: 'c'.repeat(64),
  bundle: '/plugins/timer',
  enabled: true,
  next: 'the Extensions surface holds the switch and the mount for this bundle',
})

const call = (name: string, args: Record<string, unknown>, result?: string) => ({
  id: `${name}-${result ? 'done' : 'start'}`,
  name,
  args,
  result,
  status: result ? 'done' : 'pending',
})

const SCAFFOLD_CALL = call('create_plugin_scaffold', { name: 'timer' }, SCAFFOLD)
const WRITE_CALL = call(
  'write_plugin_source',
  { bundle: 'timer', path: 'ui/app.js' },
  '{"path":"ui/app.js"}',
)
const VERIFY_CALL = call('verify_plugin_bundle', { bundle: 'timer' }, VERIFIED)
const INSTALL_CALL = call('install_plugin_bundle', { bundle: 'timer' }, INSTALLED)
const TURN = [SCAFFOLD_CALL, WRITE_CALL, VERIFY_CALL, INSTALL_CALL]

const ENTRY = {
  id: 'timer',
  name: 'timer',
  enabled: true,
  surface: { type: 'floating-window', entry: 'ui/index.html', title: 'timer' },
}

beforeEach(() => {
  apiMocks.getPlugins.mockReset()
  surfaceMocks.show.mockReset()
  surfaceMocks.isOpen.mockReset().mockReturnValue(false)
  surfaceMocks.hide.mockReset()
})

describe('CreatorCard (issue #28)', () => {
  it('renders nothing for a turn without a creator call', () => {
    render(<CreatorCard tools={[call('read_file', { path: 'a.ts' }, 'text')]} />)
    expect(document.querySelector('[data-testid="creator-card"]')).toBeNull()
  })

  it('names the bundle and lists the files the answers showed', () => {
    render(<CreatorCard tools={[SCAFFOLD_CALL, WRITE_CALL]} streaming />)
    const card = screen.getByTestId('creator-card')
    expect(card.textContent).toContain('timer')
    expect(screen.getAllByTestId('creator-file').map((el) => el.textContent)).toEqual([
      'ephe-plugin.json',
      'ui/app.css',
      'ui/app.js',
      'ui/index.html',
    ])
    expect(card.textContent).toContain('0.1.0')
  })

  it('says a step is still running only while the stream is open', () => {
    const pending = [
      call('create_plugin_scaffold', { name: 'timer' }, SCAFFOLD),
      call('install_plugin_bundle', { bundle: 'timer' }),
    ]
    const { unmount } = render(<CreatorCard tools={pending} streaming />)
    expect(screen.getByTestId('creator-running')).toBeTruthy()
    unmount()
    render(<CreatorCard tools={[SCAFFOLD_CALL]} streaming={false} />)
    expect(document.querySelector('[data-testid="creator-running"]')).toBeNull()
  })

  it('shows the verification problems in the words the check used', () => {
    const refused = call(
      'verify_plugin_bundle',
      { bundle: 'timer' },
      JSON.stringify({
        ok: false,
        error: 'manifest_invalid',
        bundle: '/tmp/creator/plugins/timer',
        sha256: 'b'.repeat(64),
        problems: ["tool 'run': entry file is missing"],
        next: 'ship the file each entry names, inside the bundle',
      }),
    )
    render(<CreatorCard tools={[SCAFFOLD_CALL, refused]} />)
    expect(screen.getByTestId('creator-problem').textContent).toContain(
      "tool 'run': entry file is missing",
    )
    expect(document.querySelector('[data-testid="creator-open-surface"]')).toBeNull()
  })

  it('offers the open action once the install answer says installed', () => {
    render(<CreatorCard tools={TURN} />)
    expect(screen.getByTestId('creator-open-surface')).toBeTruthy()
    expect(apiMocks.getPlugins).not.toHaveBeenCalled()
  })

  it('mounts the surface the store declares for the bundle', async () => {
    apiMocks.getPlugins.mockResolvedValue({ public: [ENTRY], personal: [] })
    surfaceMocks.show.mockResolvedValue({
      opened: true,
      side: 'overlay',
      created: true,
      handle: 'timer',
      unmet: [],
      note: '',
      message: '',
    })
    render(<CreatorCard tools={TURN} />)
    fireEvent.click(screen.getByTestId('creator-open-surface'))
    await waitFor(() => expect(apiMocks.getPlugins).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(surfaceMocks.show).toHaveBeenCalledWith(
        { pluginId: 'timer', descriptor: ENTRY.surface },
        expect.any(Function),
      ),
    )
    expect(screen.getByTestId('creator-open-state').textContent).toContain('timer')
  })

  it('reads a refused mount out loud instead of swallowing it', async () => {
    apiMocks.getPlugins.mockResolvedValue({ public: [ENTRY], personal: [] })
    surfaceMocks.show.mockResolvedValue({
      opened: false,
      side: null,
      created: false,
      handle: '',
      unmet: [],
      note: '',
      message: 'surface.cannotMount',
    })
    render(<CreatorCard tools={TURN} />)
    fireEvent.click(screen.getByTestId('creator-open-surface'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('surface.cannotMount')
  })

  it('says so when the installed bundle declares no surface', async () => {
    apiMocks.getPlugins.mockResolvedValue({
      public: [{ ...ENTRY, surface: undefined }],
      personal: [],
    })
    render(<CreatorCard tools={TURN} />)
    fireEvent.click(screen.getByTestId('creator-open-surface'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('chat.creator.noSurface')
    expect(surfaceMocks.show).not.toHaveBeenCalled()
  })

  it('says so when the store has no row for the bundle', async () => {
    apiMocks.getPlugins.mockResolvedValue({ public: [], personal: [] })
    render(<CreatorCard tools={TURN} />)
    fireEvent.click(screen.getByTestId('creator-open-surface'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('chat.creator.notListed')
  })

  it('keeps the read error visible when the store view fails', async () => {
    apiMocks.getPlugins.mockRejectedValue(new Error('boom'))
    render(<CreatorCard tools={TURN} />)
    fireEvent.click(screen.getByTestId('creator-open-surface'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('boom')
  })
})
