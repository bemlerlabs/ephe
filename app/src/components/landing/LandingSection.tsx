import type { ReactNode } from 'react'

/** One numbered section of the page: an eyebrow, one title, one explanatory line. */
export function LandingSection({
  id,
  eyebrow,
  title,
  lede,
  children,
}: {
  id: string
  eyebrow: string
  title: string
  lede?: string
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="mt-16 scroll-mt-6 sm:mt-20">
      <p className="font-mono text-ui-2xs uppercase tracking-[0.18em] text-ink-faint">{eyebrow}</p>
      <h2
        id={`${id}-title`}
        className="mt-2 font-display text-2xl tracking-tight text-foreground sm:text-3xl"
      >
        {title}
      </h2>
      {lede ? (
        <p className="mt-3 max-w-2xl text-ui-sm leading-relaxed text-ink-soft">{lede}</p>
      ) : null}
      <div className="mt-6">{children}</div>
    </section>
  )
}
