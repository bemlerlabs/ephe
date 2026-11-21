/**
 * The audio card on the activity rail.
 *
 * A `file_result` event carries the server's own sentence and, for a WAV, the code
 * that names what the file is. The rail shows the reader's language for that code;
 * without one it shows what the server said, and with neither it says which kind of
 * file landed at which path.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { artifactLabel, artifactName } = vi.hoisted(() => ({
  artifactLabel: vi.fn(),
  artifactName: vi.fn((path: string) => path.split('/').filter(Boolean).pop() ?? path),
}))
vi.mock('@/lib/artifactLabel', () => ({ artifactLabel, artifactName }))

import { applyStreamEvent } from './streamActions'
import type { StreamEvent } from '@/types'

/** Only the action the file_result case reaches; the reducer's other arms stay untouched. */
function mockStore() {
  return { upsertActivity: vi.fn() }
}

function run(event: StreamEvent, store: ReturnType<typeof mockStore>) {
  applyStreamEvent(event, store as unknown as Parameters<typeof applyStreamEvent>[1])
}

describe('file_result on the activity rail', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
    artifactLabel.mockReset()
    artifactName.mockClear()
  })

  it('asks the card reader for the code the server sent', () => {
    artifactLabel.mockReturnValue('card in the reader language')
    run(
      {
        type: 'file_result',
        file_type: 'audio',
        path: '/Users/me/artifacts/calm.wav',
        label: '🎵 Music bed: calm.wav',
        label_code: 'audioMusicBed',
      },
      store,
    )
    expect(artifactLabel).toHaveBeenCalledWith(
      'audioMusicBed',
      { name: 'calm.wav' },
      '🎵 Music bed: calm.wav',
    )
    expect(store.upsertActivity).toHaveBeenCalledWith({
      label: 'card in the reader language',
      status: 'done',
      path: '/Users/me/artifacts/calm.wav',
      fileType: 'audio',
      artifactId: undefined,
    })
  })

  it('falls back to kind and path when nothing names the file', () => {
    artifactLabel.mockReturnValue('')
    run({ type: 'file_result', file_type: 'audio', path: '/out/t.wav' }, store)
    expect(store.upsertActivity).toHaveBeenCalledWith({
      label: 'audio: /out/t.wav',
      status: 'done',
      path: '/out/t.wav',
      fileType: 'audio',
      artifactId: undefined,
    })
  })
})
