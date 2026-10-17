/**
 * ◑ Ephe — Background (Ephemora design language, user decision 2026-10-01)
 *
 * The animated Black Forest canvas is gone. The new design language is
 * a flat, near-black solid (#0A0A0A) — the current standard of modern
 * AI/SaaS apps (reference desktop clients): a calm, matte surface,
 * so sidebar and chat content stand out clearly. No parallax, no
 * fog/tree layers, no particles — one single, GPU-free fill.
 *
 * One source of truth for all three call sites (chat, setup, onboarding).
 */
export default function ForestBackground() {
  return (
    <div
      aria-hidden="true"
      className="fixed inset-0 z-base h-full w-full pointer-events-none"
      style={{ background: 'var(--color-background)' }}
    />
  )
}
