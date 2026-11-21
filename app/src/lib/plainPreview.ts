/**
 * The shortened history line of the automation log is a preview, not a document:
 * the agent answers in Markdown, and the list used to show that markup unfiltered
 * — `**📅 Wochenrückblick — KW 39**` — language-gate: ignore: verbatim agent output, the regression example.
 * The expanded history stays unchanged — there, fidelity to the log is the point.
 *
 * `snake_case` stays whole: '_' is removed only as markup, never inside a word —
 * `monthly_budget_2026.xlsx` is exactly the case the history shows.
 */
export function plainPreview(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#+\s*/gm, '')
    .replace(/^\s*>+\s?/gm, '')
    .replace(/(\*\*|__)(.+?)\1/g, '$2')
    .replace(/(\*|~~)(.+?)\1/g, '$2')
    .replace(/(^|[\s(])_(.+?)(_|[\s).,])/g, '$1$2$3')
    .replace(/[*~#>]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}
