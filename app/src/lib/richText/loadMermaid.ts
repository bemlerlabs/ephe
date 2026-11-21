/**
 * Mermaid is the heavier of the two renderers and arrives through the same seam
 * as KaTeX: a dynamic import, cached in module scope, never a static one.
 */
type MermaidApi = typeof import('mermaid').default

let pending: Promise<MermaidApi> | null = null

export function loadMermaid(): Promise<MermaidApi> {
  if (!pending) {
    pending = import('mermaid')
      .then(({ default: mermaid }) => {
        mermaid.initialize({
          // Diagram source is model output. `strict` sends every label through the
          // sanitizer before it becomes DOM, and `suppressErrorRendering` keeps
          // mermaid's own error graphic out of the page when a diagram does not
          // parse — the caller renders the failure itself.
          startOnLoad: false,
          securityLevel: 'strict',
          suppressErrorRendering: true,
        })
        return mermaid
      })
      .catch((err: unknown) => {
        pending = null
        throw err
      })
  }
  return pending
}
