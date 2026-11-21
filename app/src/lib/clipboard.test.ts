import { afterEach, describe, expect, it, vi } from 'vitest'
import { codeFenceHtml, copyTypedText } from './clipboard'

type Bridge = { __TAURI__?: unknown }

function shell(invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>) {
  ;(window as Bridge).__TAURI__ = { core: { invoke } }
}

function browser() {
  delete (window as Bridge).__TAURI__
}

afterEach(() => {
  browser()
  vi.restoreAllMocks()
})

describe('copyTypedText', () => {
  it('writes both faces through the shell when it is there', async () => {
    const invoke = vi.fn(async () => undefined)
    shell(invoke)

    await expect(copyTypedText('const n = 1', '<pre><code>const n = 1</code></pre>')).resolves.toBe(
      true,
    )

    expect(invoke).toHaveBeenCalledWith('write_rich_clipboard', {
      plain: 'const n = 1',
      html: '<pre><code>const n = 1</code></pre>',
    })
  })

  it('sends no HTML face when there is none to send', async () => {
    const invoke = vi.fn(async () => undefined)
    shell(invoke)

    await copyTypedText('a plain answer')

    expect(invoke).toHaveBeenCalledWith('write_rich_clipboard', {
      plain: 'a plain answer',
      html: null,
    })
  })

  it('falls back to the browser clipboard when the shell refuses', async () => {
    shell(async () => {
      throw new Error('payload above the cap')
    })
    const writeText = vi.fn(async () => undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    await expect(copyTypedText('text')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('text')
  })

  it('uses the browser clipboard directly in a PWA', async () => {
    browser()
    const writeText = vi.fn(async () => undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    await expect(copyTypedText('text')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('text')
  })

  it('reports a copy that did not happen', async () => {
    browser()
    Object.assign(navigator, {
      clipboard: {
        writeText: async () => {
          throw new Error('denied')
        },
      },
    })

    await expect(copyTypedText('text')).resolves.toBe(false)
  })
})

describe('codeFenceHtml', () => {
  it('escapes the code and keeps a known language tag', () => {
    expect(codeFenceHtml('if (a < b && c > d) {', 'ts')).toBe(
      '<pre><code class="language-ts">if (a &lt; b &amp;&amp; c &gt; d) {</code></pre>',
    )
  })

  it('drops a language tag that is not a plain word', () => {
    expect(codeFenceHtml('x', 'ts" onclick="x')).toBe('<pre><code>x</code></pre>')
  })
})
