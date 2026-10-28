/**
 * Ephe — EphemeralWordmark: the brand name as one text node.
 *
 * QD-014 B3 (owner directive 2026-10-28): the four-dot trail that used to
 * follow the name breathed forever, so the empty state read as a loading
 * animation while the agent was already `Ready`. The trail is gone; the text
 * stays ONE node so the `hero-brand` textContent pins keep matching.
 */
export default function EphemeralWordmark({
  text,
  className = '',
}: {
  text: string
  className?: string
}) {
  return (
    <span data-testid="ephemeral-wordmark" className={className}>
      {text}
    </span>
  )
}
