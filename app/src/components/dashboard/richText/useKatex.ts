import { useEffect, useState } from 'react'
import { renderKatex } from '@/lib/richText/renderKatex'
import { errorDetail } from '@/lib/richText/errorDetail'

export type MathState =
  { status: 'pending' } | { status: 'ready'; html: string } | { status: 'failed'; detail: string }

/**
 * A formula has three states because KaTeX arrives asynchronously, and the caller
 * draws all of them: without the pending one the paragraph would sit empty until
 * the chunk lands and then push everything below it down.
 */
export function useKatex(tex: string, display: boolean): MathState {
  const [state, setState] = useState<MathState>({ status: 'pending' })

  useEffect(() => {
    let live = true
    setState({ status: 'pending' })
    renderKatex(tex, display).then(
      (html) => {
        if (live) setState({ status: 'ready', html })
      },
      (err: unknown) => {
        if (live) setState({ status: 'failed', detail: errorDetail(err) })
      },
    )
    return () => {
      live = false
    }
  }, [tex, display])

  return state
}
