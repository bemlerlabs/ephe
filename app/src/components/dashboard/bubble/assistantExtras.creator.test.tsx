/**
 * #28 — the creator card in a real bubble, once.
 *
 * The contract this pins is the calm transcript's: the run line stays one, the card is
 * added beside it and is not a second copy of the rows above. A turn without a creator
 * call gets no card at all.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'
import type { ChatMessage } from '@/types'

const apiMocks = vi.hoisted(() => ({ getPlugins: vi.fn() }))

vi.mock('@/lib/api', () => ({
  getPlugins: apiMocks.getPlugins,
  fileUrl: (p: string) => `/api/files/${p}`,
  artifactFileUrl: (id: string) => `/api/artifacts/${id}`,
  synthesizeSpeech: vi.fn(() => Promise.resolve('/audio/tts.mp3')),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  getCapabilities: vi.fn(async () => ({ subagent: { tool_count: null } })),
  ApiError: class ApiError extends Error {
    status = 0
  },
}))

vi.mock('@/lib/pluginDisplay', () => ({
  isPluginSurfaceOpen: vi.fn(() => false),
  showPluginSurface: vi.fn(),
  hidePluginSurface: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
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

const tools = (streaming: boolean): ChatMessage['tool_calls'] =>
  [
    {
      id: 'c1',
      name: 'create_plugin_scaffold',
      args: { name: 'timer' },
      result: SCAFFOLD,
      status: 'done',
    },
    {
      id: 'c2',
      name: 'install_plugin_bundle',
      args: { bundle: 'timer' },
      result: streaming ? undefined : INSTALLED,
      status: streaming ? 'pending' : 'done',
    },
  ] as unknown as ChatMessage['tool_calls']

const CREATOR_TURN: ChatMessage = {
  id: 'creator',
  role: 'assistant',
  content: 'The bundle is staged and installed.',
  timestamp: Date.now() - 4000,
  streaming: false,
  tool_calls: tools(false),
  blocks: [
    { kind: 'tool', callId: 'c1' },
    { kind: 'tool', callId: 'c2' },
    { kind: 'text', text: 'The bundle is staged and installed.' },
  ],
} as ChatMessage

describe('CreatorCard wiring (issue #28)', () => {
  it('renders one card in a finished creator turn', () => {
    render(<MessageBubble message={CREATOR_TURN} />)
    expect(screen.getAllByTestId('creator-card')).toHaveLength(1)
    expect(screen.getByTestId('creator-open-surface')).toBeTruthy()
    expect(document.querySelectorAll('[data-testid="diff-summary-line"]')).toHaveLength(1)
  })

  it('holds the running line while an install has not answered', () => {
    render(
      <MessageBubble
        message={{ ...CREATOR_TURN, id: 'live', streaming: true, tool_calls: tools(true) }}
      />,
    )
    expect(screen.getByTestId('creator-running')).toBeTruthy()
    expect(document.querySelector('[data-testid="creator-open-surface"]')).toBeNull()
  })

  it('renders no card for a turn that never called the creator', () => {
    render(
      <MessageBubble
        message={
          {
            id: 'plain',
            role: 'assistant',
            content: 'Nothing was staged here.',
            timestamp: Date.now(),
            streaming: false,
            tool_calls: [
              { id: 'p1', name: 'read_file', args: { path: 'a.ts' }, result: 'x', status: 'done' },
            ] as unknown as ChatMessage['tool_calls'],
          } as ChatMessage
        }
      />,
    )
    expect(document.querySelector('[data-testid="creator-card"]')).toBeNull()
  })
})
