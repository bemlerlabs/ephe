import { loadMermaid } from './loadMermaid'
import { getStoredTheme } from '../theme'

/** Mermaid ids are global: the staging element it writes to `document.body` is
 *  named `d<id>`, so two diagrams rendering at once must not share one. */
let sequence = 0

/**
 * Draws one diagram and returns its SVG markup.
 *
 * The staging element is removed in a `finally`: mermaid cleans up after itself on
 * success only, so a page that receives broken diagrams would accumulate one
 * leftover div per failure.
 *
 * The theme is applied per call. The loader is initialised once, while the reader
 * can switch between the light and the dark surface at any time.
 */
export async function renderMermaid(code: string): Promise<string> {
  const mermaid = await loadMermaid()
  mermaid.initialize({ theme: getStoredTheme() === 'dark' ? 'dark' : 'default' })
  const id = `ephe-diagram-${++sequence}`
  try {
    const { svg } = await mermaid.render(id, code)
    return svg
  } finally {
    document.getElementById(`d${id}`)?.remove()
  }
}
