import type { ReactNode } from 'react'
import MermaidChart from './MermaidChart'

/**
 * The fence languages the rich renderers own.
 *
 * Returning null hands the fence back to the code path, so the caller keeps one
 * dispatch point and no renderer has to know what it is not.
 */
export function richFence(language: string | undefined, code: string): ReactNode | null {
  if (language === 'mermaid') return <MermaidChart code={code} />
  return null
}
