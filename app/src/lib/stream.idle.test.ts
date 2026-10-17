// readWithIdle: a stalled reader (no byte) must throw after ms; a feeding one must not.
import { describe, expect, it } from 'vitest'
import { readWithIdle, StreamChatError } from './stream'

function hangingReader(): ReadableStreamDefaultReader<Uint8Array> {
  // Stream without a source: enqueue/close is never called → read() hangs forever.
  return new ReadableStream<Uint8Array>().getReader()
}

describe('readWithIdle', () => {
  it('wirft StreamChatError wenn kein Byte kommt', async () => {
    await expect(readWithIdle(hangingReader(), 20)).rejects.toBeInstanceOf(StreamChatError)
  })

  it('liefert normal wenn ein Chunk ankommt', async () => {
    const reader = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new TextEncoder().encode('hi'))
        c.close()
      },
    }).getReader()
    const r = await readWithIdle(reader, 1000)
    expect(r.done).toBe(false)
    expect(new TextDecoder().decode(r.value)).toBe('hi')
  })
})
