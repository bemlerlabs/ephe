/**
 * Ephe — the adopt gesture, one mechanism for two ways in (R4/A1).
 *
 * On the desktop it opens the native "save as…" dialog; in the browser it hands
 * the server the remembered target — and when the server has none, the 422 answer
 * comes back and the surface asks for a path. Three routes, one question: where
 * should your copy go?
 */
import { adoptArtifact, type ArtifactAdoptResult } from '@/lib/api'
import { pickSaveTarget } from '@/lib/nativeDialog'

export async function adoptWithTarget(
  id: string,
  name: string,
  title?: string,
): Promise<ArtifactAdoptResult> {
  const target = await pickSaveTarget(name, title ?? 'Übernehmen')
  if (target) return adoptArtifact(id, target.path)
  return adoptArtifact(id)
}
