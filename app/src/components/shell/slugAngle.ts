/**
 * Ephe — S wave: a deterministic gradient angle for lettermark tiles.
 * The same maths as the PluginIcon fallback — one helper so tiles land
 * identically everywhere (plugin store, environment scan, onboarding).
 */
export default function slugAngle(slug: string): number {
  return [...(slug || '?')].reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % 360
}
