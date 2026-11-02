/**
 * Ephe — the ⌘K palette asked for by a click.
 *
 * The palette answers the key from one window listener (`useCommandPalette`), which is
 * what makes it the same palette on every page. A row that wants it therefore asks for
 * the key rather than reaching for state it does not own — the rail's Search row and the
 * drawer's Search row both arrive at the hook through this one door, so a click and the
 * chord cannot drift into two different palettes.
 */
export function openCommandPalette(): void {
  window.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'k', metaKey: true, ctrlKey: false, bubbles: true }),
  )
}
