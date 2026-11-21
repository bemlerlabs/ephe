'use client'

import { UserMarkdown } from '../bubble/messageMarkdown'

/**
 * The stored note of a memory row, read as the markdown it was written in.
 *
 * Measured 2026-11-01 on v0.5.2 at `#/memory`: the card printed its own source —
 * `**What I checked:**`, a pipe table, backticks around a path — because
 * `MemoryRowCard` set `row.text` into a bare `<p>`. Reading is all that changes
 * here; what the store holds stays exactly as it arrived.
 *
 * The renderer is the chat's own. `UserMarkdown` is the memoized pipeline of
 * `bubble/messageMarkdown.tsx`: that module's remark chain (`remark-gfm` for
 * tables, `remark-math` with `rehypeMathNodes`), its width-safe element
 * overrides (`TableWithScroll`, `PreWithScroll`, `CodeWithWrap`) and
 * `stripFileMarkers`. A second markdown path would drift from the first, and the
 * difference would show up between an answer and the memory of it.
 *
 * `MarkdownBody`, the assistant path, was the other candidate and fits worse: its
 * `pre` override draws `CodeBlock` chrome (copy button, grammar request) and it
 * can turn a JSON fence into a live A2UI surface. Two hundred rows of notes are
 * not the place for either.
 *
 * At a card's width, the container carries:
 *   `prose-invert` — the markdown typography `styles/globals.css` defines by hand
 *   (the typography plugin is not installed), the set the chat bubbles wear:
 *   headings, bold, list markers, table rules, links.
 *   `[overflow-wrap:anywhere]` — inherited, so every table cell gets it too. A
 *   path with no break opportunity then shrinks to the card, and the table's own
 *   scroll container stays unused.
 *   `[&_pre]:whitespace-pre-wrap` — a fenced run wraps, because the escape hatch
 *   the chat gives one is a sideways scrollbar and a list row has no room for it.
 */
export function MemoryNoteBody({ text, trash }: { text: string; trash: boolean }) {
  return (
    <div
      data-testid="memory-note-body"
      className={`flex-1 min-w-0 prose-invert text-ui-xs leading-relaxed [overflow-wrap:anywhere] [&_pre]:whitespace-pre-wrap ${
        trash ? 'text-foreground/60 line-through decoration-status-info/30' : 'text-foreground/80'
      }`}
    >
      <UserMarkdown text={text} />
    </div>
  )
}
