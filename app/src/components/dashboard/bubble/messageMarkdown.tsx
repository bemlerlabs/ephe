import { memo, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { stripFileMarkers } from '@/lib/fileMarkers'
import { artifactProxyUrl } from '@/lib/api'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { rehypeMathNodes } from '@/lib/richText/rehypeMathNodes'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import CodeBlock from '../CodeBlock'
import A2UIRenderer from '../A2UIRenderer'
import { parseA2UI } from '../A2UIRenderer'
import { MathBlock, MathInline } from '../richText/MathFormula'
import { richFence } from '../richText/richFence'

/** M10: flatten React children to plain text (for the A2UI detection).
 *  ReactMarkdown hands the `pre` override the rendered `code` element, not a
 *  string: a reader that stops at strings returns '' and every fence falls back
 *  to CodeBlock, which is how the surface stayed unreachable. */
function extractText(children: unknown): string {
  if (children == null || typeof children === 'boolean') return ''
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(extractText).join('')
  if (typeof children === 'object' && 'props' in children) {
    return extractText((children as { props?: { children?: unknown } }).props?.children)
  }
  return ''
}

/** The fence language, taken from the `language-xxx` class on the inner `code`. */
function fenceLanguage(children: unknown): string | undefined {
  const child = Array.isArray(children) ? children[0] : children
  if (child && typeof child === 'object' && 'props' in child) {
    const className = (child as { props?: { className?: string } }).props?.className
    return className ? /language-(\S+)/.exec(className)?.[1]?.toLowerCase() : undefined
  }
  return undefined
}

/** Fence source. The code element's text ends in the newline that closes its last
 *  line, which no renderer wants back. */
function fenceText(children: unknown): string {
  return extractText(children).replace(/\n$/, '')
}

/** A surface declares its nodes in a `components` array. The loose id-map form
 *  carries no such marker, so an untagged fence only becomes a surface with the
 *  array present — a pasted JSON snippet keeps its code block. */
function declaresSurface(txt: string): boolean {
  try {
    return Array.isArray((JSON.parse(txt) as { components?: unknown }).components)
  } catch {
    return false
  }
}

/** P6 (ref-01/user request): links inside the chat open the panel URL pane instead
 *  of a foreign tab — http(s) and internal /-paths are intercepted,
 *  other schemes (mailto: …) are left to the browser default. */
const PANEL_LINK_TARGET = /^(https?:\/\/|\/)/i
function panelLinkComponents() {
  return {
    a: (props: React.ComponentProps<'a'>) => (
      <a
        {...props}
        title={props.href ?? undefined}
        onClick={(e) => {
          const href = props.href ?? ''
          if (PANEL_LINK_TARGET.test(href)) {
            e.preventDefault()
            window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: href } }))
          }
        }}
      />
    ),
  }
}

/** P1-6: module constant — a new array identity per render would defeat every
 *  memoization of the Markdown pipeline.
 *
 *  remark-math tokenizes `$…$` before Markdown's escape rules run, so a formula
 *  keeps the backslashes it needs (`\{`, `\%`, `\\`); `rehypeMathNodes` turns its
 *  output into the elements below. */
const REMARK_PLUGINS = [remarkGfm, remarkMath]

/** The formula elements `rehypeMathNodes` emits. The cast covers the tag
 *  names: `Components` knows the HTML element names, and these two are ours. */
const MATH_COMPONENTS = {
  'math-inline': MathInline,
  'math-block': MathBlock,
} as unknown as Components

/** Also a module constant, for the reason above: the plugin chain is re-run on
 *  every re-parse, and a fresh array per render re-parses every finished bubble. */
const MATH_REHYPE = [rehypeMathNodes]

/* W3-49: `body { overflow-x: hidden }` (globals.css) clips whatever a bubble
   pushes past its own edge. On a phone a wide GFM table loses its far columns,
   a long code line is cut off, a large image disappears. Each wide element
   therefore carries its own scroll container or width cap; the overrides are
   shared by the assistant path and the user path, since user bubbles render
   markdown too. */

/** Join class names without pulling in `cn` (a mocked `@/lib/utils` in tests
 *  must not be able to break this module at import time). */
function cls(...parts: Array<string | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/** GFM table: keep the far columns reachable instead of clipped. */
function TableWithScroll(props: React.ComponentProps<'table'>) {
  return (
    <div className="my-2 max-w-full overflow-x-auto">
      <table {...props} className={cls('border-collapse text-ui-xs', props.className)} />
    </div>
  )
}

/** Fenced code on the user path (no CodeBlock chrome): a raw <pre> has
 *  `white-space: pre`, so a long line overflows unless the block scrolls. */
function PreWithScroll(props: React.ComponentProps<'pre'>) {
  return <pre {...props} className={cls('max-w-full overflow-x-auto', props.className)} />
}

/** Image: a width cap — a screenshot wider than the phone keeps its ratio
 *  instead of poking past the bubble (and being clipped by `overflow-x: hidden`).
 *
 *  A remote src goes through the server's guarded proxy: the CSP allows
 *  `'self'` only, so loading it directly leaves an alt-text placeholder. When
 *  the bytes do not arrive, the message says so and offers a retry instead of
 *  showing the bare alt text. */
function MarkdownImage(props: React.ComponentProps<'img'>) {
  const { t } = useTranslation()
  const [broken, setBroken] = useState(false)
  const [retry, setRetry] = useState(0)
  const raw = props.src ?? ''
  const remote = /^https?:\/\//i.test(raw)
  const base = remote ? artifactProxyUrl(raw) : raw
  const src = retry ? `${base}${base.includes('?') ? '&' : '?'}retry=${retry}` : base
  if (broken) {
    return (
      <span
        role="alert"
        data-testid="markdown-image-unavailable"
        className="my-2 inline-flex items-center gap-2 rounded-md border border-status-warning/40 bg-status-warning/10 px-2 py-1.5 text-ui-xs text-foreground/85"
      >
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-status-warning" aria-hidden="true" />
        {t('artifacts.imageUnavailable')}
        <button
          type="button"
          onClick={() => {
            setBroken(false)
            setRetry((value) => value + 1)
          }}
          className="rounded px-1 py-0.5 text-ui-2xs font-medium text-brand-deep hover:bg-brand/10"
        >
          {t('artifacts.previewRetry')}
        </button>
      </span>
    )
  }
  return (
    <img
      {...props}
      src={src}
      onError={() => setBroken(true)}
      className={cls('max-w-full h-auto', props.className)}
    />
  )
}

/** Inline code: a monospace run without break opportunities (hash, URL, path,
 *  traceback) has to wrap, or it drags the paragraph past the bubble. The
 *  class is a no-op on block code, whose `<pre>` keeps `white-space: pre`. */
function CodeWithWrap(props: React.ComponentProps<'code'>) {
  return <code {...props} className={cls('[overflow-wrap:anywhere]', props.className)} />
}

/** User bubble markdown (G1.5): same overflow-safe overrides, no highlighting. */
const USER_COMPONENTS = {
  ...MATH_COMPONENTS,
  table: TableWithScroll,
  pre: PreWithScroll,
  img: MarkdownImage,
  code: CodeWithWrap,
}

/**
 * P1-6 (streaming perf): memoized Markdown pipeline.
 *
 * ReactMarkdown re-parses the whole text on EVERY render. While streaming, only
 * the active message's text changes per chunk — all finished bubbles (and the
 * active one's 1-s ticks) must not re-parse. memo on `text` catches that;
 * `highlight` rides along to the fence renderer: off while streaming (fences
 * stay uncoloured but readable, and no grammar is requested), on at finalize.
 */
interface MarkdownBodyProps {
  text: string
  highlight: boolean
  /** Main content path: fenced ```a2ui-JSON becomes the component surface */
  detectA2UI?: boolean
}
export const MarkdownBody = memo(function MarkdownBody({
  text,
  highlight,
  detectA2UI,
}: MarkdownBodyProps) {
  const components = useMemo(
    () => ({
      ...panelLinkComponents(),
      ...MATH_COMPONENTS,
      pre: (props: React.ComponentProps<'pre'>) => {
        // A fence the rich renderers own is drawn before anything else looks at
        // it; the rest stay on the code path below.
        const rich = richFence(fenceLanguage(props.children), fenceText(props.children))
        if (rich) return rich
        if (detectA2UI) {
          // M10: A2UI detection — a fenced surface becomes a real component
          // surface, anything else stays code. The fence is either tagged
          // `a2ui`, or its JSON declares the `components` array of a surface.
          const txt = extractText(props.children)
          const tagged = fenceLanguage(props.children) === 'a2ui'
          const surface = tagged || declaresSurface(txt) ? parseA2UI(txt) : null
          if (surface) return <A2UIRenderer json={txt} />
        }
        return <CodeBlock highlight={highlight}>{props.children}</CodeBlock>
      },
      // W3-49: wide markdown (table/code/image) stays reachable inside the
      // bubble — see the overrides above.
      table: TableWithScroll,
      img: MarkdownImage,
      code: CodeWithWrap,
    }),
    [detectA2UI, highlight],
  )
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={MATH_REHYPE}
      components={components}
    >
      {stripFileMarkers(text)}
    </ReactMarkdown>
  )
})

/** P1-6: user bubbles without highlighting/overrides — memoized so that
 *  list re-renders (virtualizer/editing state) do not re-parse. */
export const UserMarkdown = memo(function UserMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={MATH_REHYPE}
      components={USER_COMPONENTS}
    >
      {stripFileMarkers(text)}
    </ReactMarkdown>
  )
})
