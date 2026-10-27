/**
 * N7 — the text inside an attached image, read by the shell.
 *
 * The command takes the data URL the composer already holds, so a pasted
 * screenshot needs no temporary file and no upload. A browser has no Vision
 * framework and answers `null`; an image without text does too.
 */
import { tauriInvoke } from './tauriBridge'

export async function ocrImageText(dataUrl: string): Promise<string | null> {
  const invoke = tauriInvoke()
  if (!invoke || !dataUrl) return null
  try {
    const text = await invoke('extract_image_text', { image: dataUrl })
    if (typeof text !== 'string') return null
    const trimmed = text.trim()
    return trimmed ? trimmed : null
  } catch {
    return null
  }
}
