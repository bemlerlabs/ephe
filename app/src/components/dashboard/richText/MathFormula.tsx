import { memo, type ReactNode } from 'react'
import { useKatex } from './useKatex'
import RenderNote from './RenderNote'

/** The formula source travels as the element's text child. Flattened here because
 *  the child arrives as a bare string for a simple formula and as an array once
 *  anything else sits in the same node. */
function mathSource(children: ReactNode): string {
  if (typeof children === 'string') return children
  if (Array.isArray(children)) return children.map((child) => mathSource(child)).join('')
  return ''
}

/** Inline formula: keeps the paragraph's own line box, so a formula inside a
 *  sentence does not become a block. */
export const MathInline = memo(function MathInline({ children }: { children?: ReactNode }) {
  const tex = mathSource(children)
  const state = useKatex(tex, false)

  if (state.status === 'failed') {
    return <RenderNote kind="math" detail={state.detail} source={tex} />
  }
  if (state.status === 'pending') {
    return (
      <span data-math-state="pending" className="font-mono text-ink-soft">
        {tex}
      </span>
    )
  }
  // KaTeX's own markup for the formula, never the formula itself: `renderToString`
  // emits spans, and `trust: false` keeps a URL out of the result.
  return <span data-math-state="ready" dangerouslySetInnerHTML={{ __html: state.html }} />
})

/** Display formula: its own line, and wide enough matrices scroll inside it. */
export const MathBlock = memo(function MathBlock({ children }: { children?: ReactNode }) {
  const tex = mathSource(children)
  const state = useKatex(tex, true)

  if (state.status === 'failed') {
    return <RenderNote kind="math" detail={state.detail} source={tex} />
  }
  return (
    <div data-math-state={state.status} className="my-3 max-w-full overflow-x-auto text-center">
      {state.status === 'ready' ? (
        <span dangerouslySetInnerHTML={{ __html: state.html }} />
      ) : (
        <span className="font-mono text-ink-soft">{tex}</span>
      )}
    </div>
  )
})
