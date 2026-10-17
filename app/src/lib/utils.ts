import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'
import { intlLocale } from './dateLocale'

/** The namespaces the type steps of this sheet stand in: `--text-ui-*` for the
 *  interface steps and `--text-scale-*` for the reading steps. A step written in
 *  a later wave lands under one of them and is read by the rule below, so no
 *  step needs a line of its own here. */
const TYPE_STEP_NAMESPACES = ['ui', 'scale'] as const

/** `text-ui-xs`, `text-scale-data`, `text-ui-input` — a size step, never an ink. */
const TYPE_STEP = new RegExp(`^(?:${TYPE_STEP_NAMESPACES.join('|')})-\\w[\\w-]*$`)

/** tailwind-merge builds its font-size group out of the `text` theme key and
 *  hands every other `text-…` class to the colour group, whose own validator
 *  accepts any value at all. To the merge, `text-ui-xs` was a colour:
 *  `cn('text-ui-xs', 'text-ink-faint')` came back as `text-ink-faint`, and the
 *  step left the DOM with no error, no warning, and no class in the panel. 838
 *  lines over 137 files put a step and a colour in one merged string, seven
 *  primitives among them. A validator under that same theme key is tried ahead
 *  of the colour group's catch-all, so this one entry covers every step of both
 *  namespaces — the eleven the sheet declares today and any added later.
 *  Colours still beat colours and sizes still beat sizes; a step now also wins
 *  over a `leading-*` that stands before it, which is what the line-height each
 *  step pairs with its own size means, and what `text-sm` has always done. */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: [(classPart: string) => TYPE_STEP.test(classPart)],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Clock time in the language of the surface, measured against CLDR:
 * „14:35" (de-DE) and „2:35 PM" (en-US). The locale used to be pinned to
 * `de-DE`, so every chat bubble of an English interface carried the German
 * time convention. `timeStyle: 'short'` rather than `hour: '2-digit'`: the
 * latter forces en-US into the zero-padded „02:35 PM", while the short style
 * keeps the German reading exactly as it was, including „09:05". */
export function formatTime(date: Date | string, language?: string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleTimeString(intlLocale(language), { timeStyle: 'short' })
}

export function truncate(str: string, max: number = 50): string {
  return str.length > max ? `${str.slice(0, max)}…` : str
}

export function formatMessage(content: string): string {
  return content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(
      /`(.*?)`/g,
      '<code class="bg-surface-raised px-1 py-0.5 rounded text-ui-sm font-mono">$1</code>',
    )
    .replace(/\n/g, '<br />')
}
