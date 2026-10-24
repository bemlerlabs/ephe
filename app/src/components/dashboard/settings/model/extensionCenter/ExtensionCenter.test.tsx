// Extension Center: curated catalog, permission review and updates.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { ExtensionCenter } from './ExtensionCenter'
import type { SettingsModel } from '../types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMarketHome: vi.fn(),
    getMarketIndex: vi.fn(),
    getMarketInstalled: vi.fn(),
    getMarketUpdates: vi.fn(),
    planMarketInstall: vi.fn(),
    installMarketPlan: vi.fn(),
    rollbackMarketPlugin: vi.fn(),
    removeMarketPlugin: vi.fn(),
  }
})

import * as api from '@/lib/api'

const plugin = {
  name: 'alpha',
  displayName: 'Alpha',
  description: { en: 'Alpha plugin', de: 'Alpha-Plugin' },
  publisher: { name: 'Test' },
  trust: 'local',
  categories: ['code'],
  versions: [
    {
      version: '1.0.0',
      publishTimestamp: 0,
      source: { type: 'zip', url: 'artifacts/alpha.zip', sha256: 'a'.repeat(64) },
      engines: { ephe: '>=0.1.0' },
      permissions: { tool_families: ['read'], data_roots: [] },
      components: ['skills'],
    },
  ],
}

const home = {
  sources: [
    {
      id: 'bundled',
      title: 'Ephe bundled',
      kind: 'bundled' as const,
      url: '',
      trust: 'bundled',
      removable: false,
    },
  ],
  last_read: {},
  last_error: {},
}

function model(): SettingsModel {
  return {
    t: (key: string, params?: Record<string, string>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
    i18n: { language: 'en' },
  } as unknown as SettingsModel
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getMarketHome).mockResolvedValue(home as never)
  vi.mocked(api.getMarketIndex).mockResolvedValue({
    status: 'ok',
    source: home.sources[0],
    index: { format: 2, name: 'test', owner: { name: 'Test' }, plugins: [plugin] },
    error: '',
  } as never)
  vi.mocked(api.getMarketInstalled).mockResolvedValue({ plugins: [] } as never)
  vi.mocked(api.getMarketUpdates).mockResolvedValue({ updates: [], errors: [] } as never)
  vi.mocked(api.installMarketPlan).mockResolvedValue({
    status: 'extracted',
    name: 'alpha',
    version: '1.0.0',
  } as never)
})

describe('Extension Center', () => {
  it('lists a plugin and opens its details', async () => {
    render(<ExtensionCenter model={model()} view="discover" />)
    expect(await screen.findByTestId('market-plugin-alpha')).toBeTruthy()
    fireEvent.click(screen.getByTestId('market-detail-alpha'))
    expect(screen.getByTestId('market-detail-body-alpha').textContent).toContain(
      'settings.marketPublisher',
    )
  })

  it('asks for trust before an unsigned install and then installs', async () => {
    vi.mocked(api.planMarketInstall).mockResolvedValue({
      status: 'ready',
      name: 'alpha',
      version: '1.0.0',
      sha256: 'a'.repeat(64),
      url: 'artifacts/alpha.zip',
      trust: 'local',
    } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    fireEvent.click(await screen.findByTestId('market-install-alpha'))
    expect(screen.getByTestId('market-review')).toBeTruthy()
    expect(api.planMarketInstall).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('market-approve'))
    await waitFor(() =>
      expect(api.planMarketInstall).toHaveBeenCalledWith('bundled', 'alpha', '1.0.0', {
        approvePermissions: true,
        allowLocalTrust: true,
      }),
    )
    await waitFor(() => expect(api.installMarketPlan).toHaveBeenCalled())
  })

  it('shows the permission delta from a 428 before installing', async () => {
    const delta = {
      tool_families_added: ['network'],
      tool_families_removed: [],
      data_roots_added: [],
      data_roots_removed: [],
      digest: 'd1',
    }
    const signed = {
      ...plugin.versions[0]!,
      version: '2.0.0',
      source: { ...plugin.versions[0]!.source, signature: { alg: 'ES256', signature: 'x' } },
    }
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: {
        format: 2,
        name: 'test',
        owner: { name: 'Test' },
        plugins: [{ ...plugin, versions: [signed] }],
      },
      error: '',
    } as never)
    vi.mocked(api.getMarketUpdates).mockResolvedValue({
      updates: [
        {
          name: 'alpha',
          version: '2.0.0',
          installed_version: '1.0.0',
          trust: 'local',
          source_id: 'bundled',
          source_title: 'Ephe bundled',
        },
      ],
      errors: [],
    } as never)
    vi.mocked(api.planMarketInstall)
      .mockRejectedValueOnce(
        new api.ApiError('permission review', 428, 'permission_review', {
          code: 'permission_review',
          delta,
        }),
      )
      .mockResolvedValueOnce({
        status: 'ready',
        name: 'alpha',
        version: '2.0.0',
        sha256: 'b'.repeat(64),
        url: 'artifacts/alpha.zip',
        trust: 'local',
      } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    fireEvent.click(await screen.findByTestId('market-update-alpha'))
    expect(await screen.findByTestId('market-review')).toBeTruthy()
    fireEvent.click(screen.getByTestId('market-approve'))
    await waitFor(() => expect(api.installMarketPlan).toHaveBeenCalled())
  })

  it('updates from the updates view', async () => {
    const signed = {
      ...plugin.versions[0]!,
      version: '2.0.0',
      source: { ...plugin.versions[0]!.source, signature: { alg: 'ES256', signature: 'x' } },
    }
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: {
        format: 2,
        name: 'test',
        owner: { name: 'Test' },
        plugins: [{ ...plugin, versions: [signed] }],
      },
      error: '',
    } as never)
    vi.mocked(api.getMarketUpdates).mockResolvedValue({
      updates: [
        {
          name: 'alpha',
          version: '2.0.0',
          installed_version: '1.0.0',
          trust: 'local',
          source_id: 'bundled',
          source_title: 'Ephe bundled',
        },
      ],
      errors: [],
    } as never)
    vi.mocked(api.planMarketInstall).mockResolvedValue({
      status: 'ready',
      name: 'alpha',
      version: '2.0.0',
      sha256: 'b'.repeat(64),
      url: 'artifacts/alpha.zip',
      trust: 'local',
    } as never)
    render(<ExtensionCenter model={model()} view="updates" />)
    fireEvent.click(await screen.findByText('settings.marketUpdate'))
    await waitFor(() => expect(api.planMarketInstall).toHaveBeenCalled())
    await waitFor(() => expect(api.installMarketPlan).toHaveBeenCalled())
  })

  it('shows a bundled skill pack without an install action', async () => {
    const skillPack = {
      name: 'dev-pack',
      displayName: 'Development',
      description: { en: 'Development skill pack' },
      publisher: { name: 'Ephe', verified: true },
      trust: 'bundled',
      kind: 'skill-pack' as const,
      quality_label: 'bundled' as const,
      provenance: 'first-party',
      tiers: { A: 19, B: 20, C: 12 },
      categories: ['skills'],
      versions: [
        {
          version: '1.0.0',
          publishTimestamp: 0,
          source: {
            type: 'zip' as const,
            url: 'artifacts/dev-pack-1.0.0.zip',
            sha256: 'c'.repeat(64),
          },
          engines: { ephe: '>=0.1.3' },
          permissions: {},
          components: ['skills'],
        },
      ],
    }
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: { format: 2, name: 'test', owner: { name: 'Ephe' }, plugins: [skillPack] },
      error: '',
    } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    expect(await screen.findByTestId('market-plugin-dev-pack')).toBeInTheDocument()
    expect(screen.queryByTestId('market-install-dev-pack')).not.toBeInTheDocument()
    expect(screen.getAllByText('settings.marketBundledState').length).toBeGreaterThan(0)
    expect(screen.getByTestId('market-quality-dev-pack').textContent).toContain(
      'settings.marketQualityBundled',
    )
    expect(screen.getByTestId('market-quality-dev-pack').parentElement?.textContent).toContain(
      'A 19 · B 20 · C 12',
    )
  })

  it('offers a bundled third-party pack for install into the profile', async () => {
    const thirdParty = {
      ...plugin,
      name: 'superpowers',
      displayName: 'Superpowers',
      trust: 'bundled',
      kind: 'skill-pack' as const,
      quality_label: 'bundled' as const,
      provenance: 'third-party',
    }
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: { format: 2, name: 'test', owner: { name: 'Ephe' }, plugins: [thirdParty] },
      error: '',
    } as never)
    vi.mocked(api.planMarketInstall).mockResolvedValue({
      status: 'ready',
      name: 'superpowers',
      version: '1.0.0',
      sha256: 'd'.repeat(64),
      url: 'artifacts/superpowers-1.0.0.zip',
      trust: 'bundled',
    } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    fireEvent.click(await screen.findByTestId('market-install-superpowers'))
    expect(screen.getByTestId('market-review')).toBeTruthy()
    fireEvent.click(screen.getByTestId('market-approve'))
    await waitFor(() => expect(api.planMarketInstall).toHaveBeenCalled())
    await waitFor(() => expect(api.installMarketPlan).toHaveBeenCalled())
  })

  it('offers the third-party pack while the five first-party packs stay bundled', async () => {
    const packs = ['business-pack', 'dev-pack', 'office-pack', 'research-pack', 'writing-pack']
    const entries = packs.map((name) => ({
      ...plugin,
      name,
      displayName: name,
      trust: 'bundled',
      kind: 'skill-pack' as const,
      quality_label: 'bundled' as const,
      provenance: 'first-party',
    }))
    entries.push({
      ...plugin,
      name: 'superpowers',
      displayName: 'Superpowers',
      trust: 'bundled',
      kind: 'skill-pack' as const,
      quality_label: 'bundled' as const,
      provenance: 'third-party',
    })
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: { format: 2, name: 'test', owner: { name: 'Ephe' }, plugins: entries },
      error: '',
    } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    expect(await screen.findByTestId('market-install-superpowers')).toBeInTheDocument()
    for (const name of packs) {
      expect(screen.queryByTestId(`market-install-${name}`)).not.toBeInTheDocument()
      expect(screen.getByTestId(`market-quality-${name}`)).toHaveTextContent(
        'settings.marketQualityBundled',
      )
    }
  })

  it('labels a capability preset and shows unmeasured status', async () => {
    const preset = {
      ...plugin,
      name: 'image-studio',
      displayName: 'Image Studio',
      trust: 'bundled',
      quality_label: 'capability-preset' as const,
      provenance: 'first-party',
    }
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: { format: 2, name: 'test', owner: { name: 'Ephe' }, plugins: [preset] },
      error: '',
    } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    expect(await screen.findByTestId('market-quality-image-studio')).toHaveTextContent(
      'settings.marketQualityCapabilityPreset',
    )
    expect(screen.getByTestId('market-measured-image-studio')).toHaveTextContent(
      'settings.marketMeasuredNo',
    )
    expect(screen.queryByTestId('market-install-image-studio')).not.toBeInTheDocument()
    expect(screen.getByTestId('market-plugin-image-studio')).toHaveTextContent(
      'settings.marketBundledState',
    )
    expect(screen.getByTestId('market-plugin-image-studio')).not.toHaveTextContent(
      'settings.marketUnsigned',
    )
  })

  it('labels a measured plugin with engine, cases and pass3', async () => {
    const measured = {
      ...plugin,
      name: 'documents',
      displayName: 'Documents',
      quality_label: 'plugin' as const,
      provenance: 'first-party',
      measurement: {
        model: 'nvidia/nemotron-3-ultra-550b-a55b:free',
        cases: 10,
        runs: 3,
        pass3: '9/10',
      },
    }
    vi.mocked(api.getMarketIndex).mockResolvedValue({
      status: 'ok',
      source: home.sources[0],
      index: { format: 2, name: 'test', owner: { name: 'Ephe' }, plugins: [measured] },
      error: '',
    } as never)
    render(<ExtensionCenter model={model()} view="discover" />)
    const line = await screen.findByTestId('market-measured-documents')
    expect(line.textContent).toContain('nvidia/nemotron-3-ultra-550b-a55b:free')
    expect(line.textContent).toContain('10')
    expect(line.textContent).toContain('9/10')
  })

  it('presents a curated catalog with no source or report controls', async () => {
    render(<ExtensionCenter model={model()} view="discover" />)
    expect(await screen.findByTestId('market-catalog')).toBeInTheDocument()
    expect(screen.getByText('settings.marketCatalogCurated')).toBeInTheDocument()
    expect(screen.queryByTestId('market-source-add')).not.toBeInTheDocument()
    expect(screen.queryByTestId('market-source-title')).not.toBeInTheDocument()
    expect(screen.queryByTestId('market-source-url')).not.toBeInTheDocument()
    expect(screen.queryByText('settings.marketSourceAdd')).not.toBeInTheDocument()
    expect(screen.queryByText(/settings\.marketReport/)).not.toBeInTheDocument()
  })
})
