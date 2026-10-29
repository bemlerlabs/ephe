/**
 * The two reading blocks of the update dialog, apart from the surface that
 * arranges them: the release notes as the feed wrote them, and one Details row.
 */
import type { ReactNode } from 'react'
import { Rule } from '@/components/ui/Rule'

/** Inline code spans in the release notes, rendered in the mono face. */
function inline(text: string): ReactNode {
  return text.split('`').map((part, index) =>
    index % 2 === 1 ? (
      <code key={index} className="bg-surface px-1 font-mono text-ui-2xs text-ink">
        {part}
      </code>
    ) : (
      part
    ),
  )
}

/** The release notes as the feed wrote them: headings, bullets, paragraphs.
 *  No markdown dependency — the release feed has carried exactly these three
 *  shapes since the first release. */
export function NotesBody({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  text.split('\n').forEach((raw, index) => {
    const line = raw.trim()
    if (!line) return
    if (line.startsWith('### ')) {
      blocks.push(
        <h4 key={index} className="mt-3 text-scale-ui font-semibold text-foreground first:mt-0">
          {line.slice(4)}
        </h4>,
      )
      return
    }
    if (line.startsWith('- ')) {
      blocks.push(
        <p key={index} className="flex gap-2 py-0.5 text-scale-ui text-ink-soft">
          <span className="mt-[0.65em] h-1 w-1 shrink-0 rounded-full bg-brand" aria-hidden="true" />
          <span className="min-w-0">{inline(line.slice(2))}</span>
        </p>,
      )
      return
    }
    blocks.push(
      <p key={index} className="py-0.5 text-scale-ui text-ink-soft">
        {inline(line)}
      </p>,
    )
  })
  return <>{blocks}</>
}

/** One line of the Details block: a rule, a label at 13px, a value on the
 *  right edge of the mono axis. */
export function DetailRow({
  label,
  value,
  mono = false,
  testId,
}: {
  label: string
  value: string
  mono?: boolean
  testId?: string
}) {
  return (
    <>
      <Rule />
      <div className="flex items-baseline gap-3 py-1.5">
        <span className="text-scale-ui text-ink-faint">{label}</span>
        <span
          data-testid={testId}
          className={`ml-auto text-right ${mono ? 'font-mono tabular-nums text-scale-data' : 'text-scale-ui'} text-ink-faint`}
        >
          {value}
        </span>
      </div>
    </>
  )
}
