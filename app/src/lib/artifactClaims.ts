/**
 * A turn that claims an image without having produced one.
 *
 * The screenshot finding (2026-10-25): the tool failed, the answer still said
 * "live generated", and two placeholders with alt text "Bild" stayed in the
 * bubble. The surface can check the claim against what the turn registered —
 * not to argue with the answer, but to stop a claim from standing unverified.
 *
 * Deliberately narrow: a verb of making in the same sentence as an image noun.
 * "I cannot generate an image" carries no past-tense claim and stays quiet.
 */
import type { ProducedFile } from '@/components/dashboard/artifacts/messageCard'

const CLAIM = /\b(generated|created|produced|drew|made)\b/i
const IMAGE = /\b(image|picture|illustration|graphic|screenshot|diagram)\b/i
const CLAIM_DE = /\b(erstellt|erzeugt|generiert|gemalt)\w*\b/i
const IMAGE_DE = /\b(Bild|Grafik|Screenshot|Diagramm)\b/i

const IMAGE_NAME = /\.(png|jpe?g|webp|gif|avif|svg)$/i
const IMAGE_KINDS = new Set(['png', 'image', 'screenshot', 'chart', 'svg', 'diagram'])

export function claimsMissingImage(text: string, files: ProducedFile[]): boolean {
  const sentences = (text ?? '').split(/[.!?\n]+/)
  const claims = sentences.some(
    (sentence) =>
      (CLAIM.test(sentence) && IMAGE.test(sentence)) ||
      (CLAIM_DE.test(sentence) && IMAGE_DE.test(sentence)),
  )
  if (!claims) return false
  return !files.some(
    (file) => IMAGE_KINDS.has(file.kind.toLowerCase()) || IMAGE_NAME.test(file.name),
  )
}
