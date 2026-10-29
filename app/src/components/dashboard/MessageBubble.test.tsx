import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen, act } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'

// mock react-markdown with a spy: counts render calls (performance proxy for memo)
let markdownRenders = 0
let lastMarkdownProps: { rehypePlugins?: unknown[]; components?: unknown } = {}
vi.mock('react-markdown', () => ({
  default: vi.fn(
    (props: { children: ReactNode; rehypePlugins?: unknown[]; components?: unknown }) => {
      markdownRenders++
      lastMarkdownProps = props
      return <div data-testid="markdown">{String(props.children)}</div>
    },
  ),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: ReactNode }) => <pre>{children}</pre>,
}))
vi.mock('@/lib/utils', () => ({
  formatTime: () => '12:00',
  // The running step now opens itself, so its detail (Badge & friends) renders
  // in these tests too — the class combiner has to exist on the mock.
  cn: (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(' '),
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  // `as never`: the mock only has to serve the signature seen at runtime
  useTranslation: (() => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (key === 'chat.ranTools') return `Ran ${values?.count} tools`
      if (key === 'chat.ranOneTool') return 'Ran 1 tool'
      return key
    },
    i18n: { language: 'de' },
  })) as never,
}))

import type { ChatMessage } from '@/types'
import rehypeHighlight from 'rehype-highlight'

function assistantMsg(content: string, streaming = false): ChatMessage {
  return {
    id: 'm1',
    role: 'assistant',
    content,
    timestamp: 0,
    streaming,
  } as ChatMessage
}

beforeEach(() => {
  markdownRenders = 0
  lastMarkdownProps = {}
})

describe('MessageBubble D2 (Memo)', () => {
  it('ist ein memoized-Component (display.name zeigt durch)', () => {
    // memo() wraps the inner function → the name is missing/inherited
    const named = (MessageBubble as unknown as { displayName?: string }).displayName
    expect(['MessageBubbleInner', undefined]).toContain(named)
  })

  it('histo-Message (stabile Referenz) rendert NUR 1× bei parent-Re-Render', () => {
    const stableMsg = assistantMsg('historischer Text')
    const { rerender } = render(<MessageBubble message={stableMsg} />)
    const first = markdownRenders
    // The parent re-renders with the SAME reference → memo has to skip
    rerender(<MessageBubble message={stableMsg} />)
    expect(markdownRenders).toBe(first)
  })

  it('aktive Message (neue Referenz pro Chunk) rendert pro Änderung erneut', () => {
    const msgV1 = assistantMsg('Hallo', true)
    const { rerender } = render(<MessageBubble message={msgV1} />)
    const afterV1 = markdownRenders
    // updateActiveMessage creates a NEW object → memo must not hold on to it
    const msgV2 = assistantMsg('Hallo Welt', true)
    act(() => {
      rerender(<MessageBubble message={msgV2} />)
    })
    expect(markdownRenders).toBeGreaterThan(afterV1)
  })
})

// ── P1-6 (streaming perf): the markdown pipeline may only re-parse per render
// when the text REALLY changed — and the fence highlighter loads only at
// finalize (a streaming message asks no grammar for its fences).

/** The gate the fence renderer hands CodeBlock. The highlighter itself hangs off
 *  CodeBlock, which has its own suite (`CodeBlock.test.tsx`). */
function fenceGate(): boolean | undefined {
  const components = lastMarkdownProps.components as {
    pre?: (props: { children?: ReactNode }) => { props?: { highlight?: boolean } }
  }
  return components.pre?.({ children: <code className="language-js">code</code> })?.props?.highlight
}

describe('MessageBubble — Markdown-Re-Parse (P1-6)', () => {
  it('neue Message-Referenz mit GLEICHEM Text parst Markdown NICHT neu', () => {
    const { rerender } = render(<MessageBubble message={assistantMsg('stabiler Text')} />)
    const first = markdownRenders
    expect(first).toBeGreaterThan(0)
    // A new object (e.g. a store update / 1-s tick) with unchanged content →
    // the MarkdownBody memo has to skip the re-parse
    rerender(<MessageBubble message={assistantMsg('stabiler Text')} />)
    expect(markdownRenders).toBe(first)
  })

  it('geänderter Text parst Markdown erneut', () => {
    const { rerender } = render(<MessageBubble message={assistantMsg('Version 1')} />)
    const first = markdownRenders
    rerender(<MessageBubble message={assistantMsg('Version 2')} />)
    expect(markdownRenders).toBeGreaterThan(first)
  })

  it('the pipeline carries the math plugin and no highlighter; finalize opens the fence gate', () => {
    const { rerender } = render(<MessageBubble message={assistantMsg('```js\ncode\n```', true)} />)
    // The math plugin rides in the chain from the first chunk; the highlighter is not a
    // rehype plugin at all any more — CodeBlock fetches it, and only once finalized.
    expect(lastMarkdownProps.rehypePlugins).toHaveLength(1)
    expect(lastMarkdownProps.rehypePlugins).not.toContain(rehypeHighlight)
    expect(fenceGate()).toBe(false)
    rerender(<MessageBubble message={assistantMsg('```js\ncode\n```', false)} />)
    expect(lastMarkdownProps.rehypePlugins).toHaveLength(1)
    expect(lastMarkdownProps.rehypePlugins).not.toContain(rehypeHighlight)
    expect(fenceGate()).toBe(true)
  })
})

// ── I6 P2c (judge gate): ToolStreamRows must show an icon + the real counter ──
// Yardstick from the reference product: each family row = chevron + icon +
// verb + counter; short rows do not stretch the card to the full column width.
describe('MessageBubble — ToolStreamRows Icon + Breite (I6 P2c-Gate)', () => {
  const shellCall = (id: string) => ({
    id,
    name: 'run_shell',
    args: { command: 'ls' },
    result: 'ok',
    status: 'completed',
  })
  function toolMsg(calls: unknown[]): ChatMessage {
    return {
      id: 'tm1',
      role: 'assistant',
      content: 'antwort',
      timestamp: 0,
      streaming: false,
      tool_calls: calls,
    } as unknown as ChatMessage
  }

  it('Familien-Zeile traegt Chevron UND ein Familien-Icon (mind. 2 svg)', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1'), shellCall('s2')])} />)
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(row.querySelectorAll('svg').length).toBeGreaterThanOrEqual(2)
  })

  it('zwei Calls derselben Familie lesen sich als eine Zeile (Ran 2 tools)', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1'), shellCall('s2')])} />)
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(row.textContent).toMatch(/Ran 2 tools|2 tools/)
  })

  it('kurze Zeilen dehnen den Abschnitt nicht auf volle Breite (inline-flex)', () => {
    render(<MessageBubble message={toolMsg([shellCall('s1')])} />)
    const section = screen.getByTestId('tool-stream-rows')
    expect(section.className).toContain('inline-flex')
    // R43: the button now carries `w-full min-w-0` (truncate inside a flex child);
    // the section width stays inline-flex, the row only fills the section.
    const btn = screen.getByTestId('tool-stream-row-shell').querySelector('button')
    expect(btn?.className.includes('w-full')).toBe(true)
    expect(btn?.className.includes('min-w-0')).toBe(true)
  })
})

// ── I6 P3-3: the artifact header must not show the file name twice ──────────
// The detector sets the title fallback = filename (core/artifact_detector.py
// _generate_title). Sessions persisted long ago keep that data shape, so the
// display deduplicates: title is only rendered when it differs.
describe('MessageBubble — Artifact-Header Dup-Fix (I6 P3-3)', () => {
  function artifactMsg(title: string, filename: string): ChatMessage {
    return {
      id: 'm1',
      role: 'assistant',
      content: 'text',
      timestamp: 0,
      artifacts: [
        {
          id: 'a1',
          artifact_type: 'code',
          content: 'const x = 1',
          language: 'js',
          title,
          filename,
        },
      ],
    } as ChatMessage
  }

  it('title === filename: Dateiname erscheint GENAU einmal im Header', () => {
    render(<MessageBubble message={artifactMsg('script.js', 'script.js')} />)
    expect(screen.getAllByText('script.js')).toHaveLength(1)
  })

  it('unterschiedlicher title: beide Texte bleiben sichtbar', () => {
    render(<MessageBubble message={artifactMsg('Palindrome Checker', 'script.js')} />)
    expect(screen.getAllByText('script.js')).toHaveLength(1)
    expect(screen.getByText('Palindrome Checker')).toBeTruthy()
  })
})

// ── R1 (2026-09-09): chronology plan — text ↔ tool in the rhythm of events ──
// The store delivers `blocks` in arrival order; the renderer has to build the DOM
// order exactly from it (text-block, tool-row, text-block).
describe('MessageBubble — StreamBlocks Chronologie (Runde 1)', () => {
  const shellCall = (id: string) => ({
    id,
    name: 'run_shell',
    args: { command: 'ls' },
    result: 'ok',
    status: 'completed',
  })

  function blockMsg(): ChatMessage {
    return {
      id: 'b1',
      role: 'assistant',
      content: 'AB',
      timestamp: 0,
      streaming: false,
      tool_calls: [shellCall('s1')] as never,
      blocks: [
        { kind: 'text', text: 'A' },
        { kind: 'tool', callId: 's1' },
        { kind: 'text', text: 'B' },
      ] as never,
    } as unknown as ChatMessage
  }

  it('DOM-Reihenfolge = [text, tool-row, text] — nicht Tools-first-Text-last', () => {
    render(<MessageBubble message={blockMsg()} />)
    const nodes = Array.from(document.querySelectorAll('[data-testid]')).map((el) =>
      el.getAttribute('data-testid')!,
    )
    const iTextA = nodes.indexOf('stream-text-block')
    const iTool = nodes.indexOf('tool-stream-row-shell')
    const iTextB = nodes.lastIndexOf('stream-text-block')
    expect(iTextA).toBeGreaterThan(-1)
    expect(iTool).toBeGreaterThan(-1)
    expect(iTextA).toBeLessThan(iTool)
    expect(iTool).toBeLessThan(iTextB)
    const textBlocks = screen.getAllByTestId('stream-text-block')
    expect(textBlocks).toHaveLength(2)
    expect(textBlocks[0]!.textContent).toContain('A')
    expect(textBlocks[1]!.textContent).toContain('B')
  })

  it('ohne blocks greift der Legacy-Pfad: kein stream-text-block, aber ToolStreamRows', () => {
    const legacy = {
      id: 'l1',
      role: 'assistant',
      content: 'legacy',
      timestamp: 0,
      streaming: false,
      tool_calls: [shellCall('x1')] as never,
    } as unknown as ChatMessage
    render(<MessageBubble message={legacy} />)
    expect(screen.queryAllByTestId('stream-text-block')).toHaveLength(0)
    expect(screen.getByTestId('tool-stream-row-shell')).toBeTruthy()
  })
})

// ── R42 (round 2): live cadence in the aggregated row — the user sees the
// progress while the tools run (done/total pair + stdout tail), instead of
// only after expanding. Reference form: „Terminal · 2/3  LAST-OUT".
describe('MessageBubble — Live-Takt in der Zeile (Runde 2 R42)', () => {
  const run = (id: string, status: string, stdout?: string) => ({
    id,
    name: 'run_shell',
    args: { command: 'ls' },
    status,
    ...(stdout ? { stdout } : {}),
  })
  function liveMsg(calls: unknown[]): ChatMessage {
    return {
      id: 'lm1',
      role: 'assistant',
      content: 'x',
      timestamp: 0,
      streaming: true,
      tool_calls: calls,
    } as unknown as ChatMessage
  }

  it('laufende Familie zeigt das done/total-Paar in der Zeile', () => {
    render(
      <MessageBubble
        message={liveMsg([run('s1', 'completed'), run('s2', 'completed'), run('s3', 'pending')])}
      />,
    )
    expect(screen.getByTestId('tool-stream-row-shell').textContent).toContain('2/3')
  })

  it('fertige Familie ist eine Zeile ohne n/m-Paar', () => {
    render(<MessageBubble message={liveMsg([run('s1', 'completed'), run('s2', 'completed')])} />)
    const row = screen.getByTestId('tool-stream-row-shell')
    expect(row.textContent).not.toContain('2/2')
  })

  it('stdout-Tail steht in der Zeile, ohne dass der Leser etwas tun muss', () => {
    render(<MessageBubble message={liveMsg([run('s1', 'pending', 'a\nb\nLAST')])} />)
    // The running step shows its last output line in the row itself; the detail
    // below it carries the full tail.
    expect(screen.getByTestId('tool-row-tail').textContent).toContain('LAST')
  })
})
