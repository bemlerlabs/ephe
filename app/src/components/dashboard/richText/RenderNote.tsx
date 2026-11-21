import { useTranslation } from 'react-i18next'

/**
 * What stands where a formula or a diagram should be.
 *
 * Two routes reach it — the source did not parse, or the renderer could not be
 * loaded — and both have to leave the reader with the same three things: a
 * sentence saying the render failed, the reason, and the source the engine sent.
 * An empty box, or a page that stops at the diagram, is the failure this component
 * exists to prevent.
 *
 * The source is rendered as text, so a hostile document stays inert.
 */
export default function RenderNote({
  kind,
  detail,
  source,
}: {
  kind: 'math' | 'diagram'
  detail: string
  source: string
}) {
  const { t } = useTranslation()
  return (
    <div
      data-rich-note={kind}
      role="note"
      className="my-3 max-w-full rounded-lg border border-hairline bg-canvas px-3 py-2"
    >
      <p className="text-ui-xs text-ink">
        {t(kind === 'math' ? 'richText.mathError' : 'richText.diagramError')}
      </p>
      {detail ? (
        <p className="mt-1 font-mono text-ui-xs break-words text-status-danger">{detail}</p>
      ) : null}
      <pre className="mt-2 max-w-full overflow-x-auto font-mono text-ui-xs break-words whitespace-pre-wrap text-ink-soft">
        {source}
      </pre>
    </div>
  )
}
