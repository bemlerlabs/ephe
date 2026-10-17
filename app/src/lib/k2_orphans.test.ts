import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  exportChatMarkdown,
  feedbackThumbsUp,
  feedbackThumbsDown,
  downloadTextFile,
} from '@/lib/api'

// K2 (2026-09-08): hook up the backend orphans — Z38 Export (POST /api/export,
// text/markdown) + Z13 Thumbs (POST /api/feedback/thumbs_up|down).

interface FakeRes {
  ok: boolean
  status: number
  json: () => Promise<unknown>
  text: () => Promise<string>
}

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string, init?: RequestInit): Promise<FakeRes> => {
    if (String(url).includes('/api/export')) {
      expect(String(init?.body ?? '')).contains('"role":"user"')
      return {
        ok: true,
        status: 200,
        json: async () => ({}),
        text: async () => '## Chat Export\n**Nutzer:** hi',
      }
    }
    if (String(url).includes('thumbs_up'))
      return { ok: true, status: 200, json: async () => ({ saved: true }), text: async () => '' }
    if (String(url).includes('thumbs_down'))
      return { ok: true, status: 200, json: async () => ({ saved: true }), text: async () => '' }
    return { ok: false, status: 404, json: async () => ({}), text: async () => '' }
  }) as unknown as typeof globalThis.fetch
})

describe('K2 Z38 — Chat-Export', () => {
  it('POST /api/export mit messages-Payload, liefert Markdown-Text zuruck', async () => {
    const md = await exportChatMarkdown([{ role: 'user', content: 'hi' }])
    expect(md).toContain('Chat Export')
    const fetchMock = globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/export')
    expect(String(init?.body)).contains('"role":"user"')
  })
})

describe('K2 Z13 — Thumbs', () => {
  it('thumbs_up POSTet prompt+response an /api/feedback/thumbs_up', async () => {
    await feedbackThumbsUp('frage', 'antwort')
    const fetchMock = globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/feedback/thumbs_up')
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>
    expect(body.prompt).toBe('frage')
    expect(body.response).toBe('antwort')
  })

  it('thumbs_down POSTet mit reason in /api/feedback/thumbs_down', async () => {
    await feedbackThumbsDown('frage', 'antwort', 'Zu lang')
    const fetchMock = globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/api/feedback/thumbs_down')
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>
    expect(body.reason).toBe('Zu lang')
  })
})

describe('K2 downloadTextFile', () => {
  it('legt einen Blob-Anker mit Download-Namen an', () => {
    const clicked: { name: string; href: string }[] = []
    const proto = HTMLAnchorElement.prototype as unknown as { click: () => void }
    const orig = proto.click
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    // jsdom 30.1 cannot build an object URL from a Blob inside the test
    // container (it reads an internal field that node does not have there). In
    // the browser that is the normal API. What the test checks is the anchor
    // with its name — not jsdom's Blob implementation.
    URL.createObjectURL = () => 'blob:ephe-test'
    URL.revokeObjectURL = () => {}
    proto.click = function (this: HTMLAnchorElement) {
      clicked.push({ name: this.getAttribute('download') ?? '', href: this.href })
    } as never
    try {
      downloadTextFile('chat.md', '# hi')
    } finally {
      proto.click = orig as never
      URL.createObjectURL = origCreate
      URL.revokeObjectURL = origRevoke
    }
    expect(clicked).toEqual([{ name: 'chat.md', href: 'blob:ephe-test' }])
  })
})
