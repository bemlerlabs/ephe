// A3: the provenance shows what it knows — and what it does not know.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import ArtifactProvenanceBlock from './provenance'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))
const artifactProvenance = vi.fn()
vi.mock('@/lib/api', async (io) => {
  const real = await io<typeof import('@/lib/api')>()
  return { ...real, artifactProvenance: (id: string) => artifactProvenance(id) }
})

beforeEach(() => {
  artifactProvenance.mockReset()
})
afterEach(cleanup)

describe('ArtifactProvenanceBlock', () => {
  it('shows the turn, the call and the tool calls of the turn', async () => {
    artifactProvenance.mockResolvedValue({
      known: true,
      turn_id: 'deadbeef0102',
      call_id: 'deadbe-0',
      args_hash: 'x',
      session_id: 's1',
      calls: [{ tool: 'create_pdf', args: 'title=Bericht', decision: 'auto', duration_ms: 812 }],
    })
    render(<ArtifactProvenanceBlock id="a1" />)
    const box = await screen.findByTestId('artifact-provenance')
    expect(box.textContent).toContain('deadbeef0102')
    expect(box.textContent).toContain('create_pdf')
    expect(box.textContent).toContain('812 ms')
  })

  it('names the gap for a card without a turn', async () => {
    artifactProvenance.mockResolvedValue({
      known: false,
      turn_id: '',
      call_id: '',
      args_hash: '',
      session_id: '',
      calls: [],
    })
    render(<ArtifactProvenanceBlock id="a2" />)
    expect((await screen.findByTestId('artifact-provenance')).textContent).toContain(
      'artifacts.page.provenance.unknown',
    )
  })

  it('shows an approval that costs something, beyond green checkmarks', async () => {
    artifactProvenance.mockResolvedValue({
      known: true,
      turn_id: 't',
      call_id: 't-1',
      args_hash: '',
      session_id: 's',
      calls: [{ tool: 'run_shell', args: 'rm -rf build', decision: 'approved', status: 'ok' }],
    })
    render(<ArtifactProvenanceBlock id="a3" />)
    await waitFor(() => expect(screen.getByText('approved')).toBeTruthy())
  })

  it('makes a failed tool call look like a failure', async () => {
    artifactProvenance.mockResolvedValue({
      known: true,
      turn_id: 't',
      call_id: 't-1',
      args_hash: '',
      session_id: 's',
      calls: [{ tool: 'create_pdf', args: 'title=x', status: 'error' }],
    })
    render(<ArtifactProvenanceBlock id="a4" />)
    await waitFor(() =>
      expect(screen.getByTestId('artifact-provenance').textContent).toContain('error'),
    )
  })

  it('says so when the chain could not be read instead of waiting', async () => {
    artifactProvenance.mockRejectedValue(new Error('offline'))
    render(<ArtifactProvenanceBlock id="a5" />)
    const box = await screen.findByTestId('artifact-provenance')
    expect(box.getAttribute('data-state')).toBe('failed')
    expect(box.textContent).toContain('artifacts.page.provenance.failed')
    // the retry goes back for the chain and shows it once it arrives
    artifactProvenance.mockResolvedValue({
      known: true,
      turn_id: 'back',
      call_id: 'back-0',
      args_hash: '',
      session_id: 's',
      calls: [],
    })
    fireEvent.click(screen.getByTestId('artifact-provenance-retry'))
    await waitFor(() =>
      expect(screen.getByTestId('artifact-provenance').textContent).toContain('back'),
    )
    expect(artifactProvenance).toHaveBeenCalledTimes(2)
  })

  it('does not hide truncated tool calls', async () => {
    const calls = Array.from({ length: 8 }, (_, i) => ({ tool: `t${i}`, status: 'ok' }))
    artifactProvenance.mockResolvedValue({
      known: true,
      turn_id: 'x',
      call_id: 'x-0',
      args_hash: '',
      session_id: 's',
      calls,
    })
    render(<ArtifactProvenanceBlock id="a6" />)
    const more = await screen.findByTestId('artifact-provenance-more')
    expect(more.textContent).toContain('artifacts.page.provenance.more')
    // the tail is not painted, the count is named instead
    expect(screen.queryByText(/t7/)).toBeNull()
  })
})
