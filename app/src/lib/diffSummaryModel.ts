/**
 * M3 (reference parity): one stats line per run — "N files changed +A −D".
 * Purely functional over the tool calls of a message; only the file family
 * (edit_file/write_file) counts. Diff results are unified diffs: lines marked
 * '+…'/'-…', with the '+++'/'---' headers excluded. write_file result lines
 * count as additions.
 */
const FILE_TOOLS = new Set(['edit_file', 'write_file'])

export type DiffSummary = { files: number; additions: number; deletions: number }

export function summarizeToolDiff(
  calls: { name: string; args?: unknown; result?: unknown }[] | undefined,
): DiffSummary | null {
  if (!calls || calls.length === 0) return null
  const paths = new Set<string>()
  let additions = 0
  let deletions = 0
  let sawFileCall = false
  for (const c of calls) {
    if (!FILE_TOOLS.has(c.name)) continue
    sawFileCall = true
    const path = (c.args as { path?: string } | undefined)?.path
    if (path) paths.add(path)
    const result = typeof c.result === 'string' ? c.result : ''
    const marked = result
      .split('\n')
      .filter(
        (l) =>
          (l.startsWith('+') && !l.startsWith('+++')) ||
          (l.startsWith('-') && !l.startsWith('---')),
      )
    if (marked.length > 0) {
      for (const line of marked) {
        if (line.startsWith('+')) additions += 1
        else deletions += 1
      }
    } else if (c.name === 'write_file') {
      // Confirmation format without diff markers: content == line count.
      additions += result.split('\n').filter((l) => l.length > 0).length
    }
  }
  if (!sawFileCall) return null
  return { files: Math.max(paths.size, 1), additions, deletions }
}
