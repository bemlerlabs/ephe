import type { ReactNode } from 'react'
import { LucideProvider } from 'lucide-react'

/** One optical stroke across every glyph; 1.5 px reads at 16, 18 and 20 px. */
export const ICON_STROKE_WIDTH = 1.5

/** The three size steps: inline text, navigation rows, section titles. */
export const ICON_SIZE = { inline: 16, navigation: 18, section: 20 } as const

export function IconScale({ children }: { children: ReactNode }) {
  return (
    <LucideProvider strokeWidth={ICON_STROKE_WIDTH} absoluteStrokeWidth>
      {children}
    </LucideProvider>
  )
}
