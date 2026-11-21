import { useEffect, useState } from 'react'
import { renderMermaid } from '@/lib/richText/renderMermaid'
import { errorDetail } from '@/lib/richText/errorDetail'
import RenderNote from './RenderNote'

type DiagramState =
  { status: 'pending' } | { status: 'ready'; svg: string } | { status: 'failed'; detail: string }

/**
 * A fenced ```mermaid block, drawn.
 *
 * The failure path is the point of this component. Mermaid throws on a diagram it
 * cannot parse, and a throw inside a render would take the message with it, so the
 * call sits in an effect and every outcome lands in state. The SVG it returns is
 * sanitized by mermaid itself under `securityLevel: 'strict'`.
 *
 * The source stands in while the renderer loads: mermaid is the largest chunk the
 * app fetches, and a bare gap in the message reads as lost text.
 */
export default function MermaidChart({ code }: { code: string }) {
  const [state, setState] = useState<DiagramState>({ status: 'pending' })

  useEffect(() => {
    let live = true
    setState({ status: 'pending' })
    renderMermaid(code).then(
      (svg) => {
        if (live) setState({ status: 'ready', svg })
      },
      (err: unknown) => {
        if (live) setState({ status: 'failed', detail: errorDetail(err) })
      },
    )
    return () => {
      live = false
    }
  }, [code])

  if (state.status === 'failed') {
    return <RenderNote kind="diagram" detail={state.detail} source={code} />
  }
  return (
    <div
      data-diagram-state={state.status}
      className="my-3 max-w-full overflow-x-auto [&>svg]:h-auto [&>svg]:max-w-full"
    >
      {state.status === 'ready' ? (
        // Mermaid's own drawing, with every label already through the sanitizer
        // that `securityLevel: 'strict'` installs. The source is not interpolated.
        <span dangerouslySetInnerHTML={{ __html: state.svg }} />
      ) : (
        <pre className="max-w-full overflow-x-auto font-mono text-ui-xs whitespace-pre-wrap text-ink-soft">
          {code}
        </pre>
      )}
    </div>
  )
}
