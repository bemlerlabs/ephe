/**
 * One copy gesture, two clipboard faces (N3).
 *
 * In the desktop shell the pasteboard is written natively with `text/plain`
 * and, when there is one, `text/html`: pasting into Notes, Mail or Slack keeps
 * the formatting, pasting into a terminal or editor keeps clean text. A browser
 * has only `navigator.clipboard.writeText`, so the plain face is the whole
 * gesture there — the same call site serves both surfaces.
 *
 * The shell command caps the payload (10 MB, `app/src-tauri/src/desktop.rs`);
 * an oversized payload or an older shell without the command falls through to
 * the browser path instead of failing the click.
 */
import { tauriInvoke } from './tauriBridge'

export async function copyTypedText(plain: string, html?: string): Promise<boolean> {
  const invoke = tauriInvoke()
  if (invoke) {
    try {
      await invoke('write_rich_clipboard', { plain, html: html ?? null })
      return true
    } catch {
      // Old shell or refused payload: the browser path below is still correct.
    }
  }
  try {
    await navigator.clipboard.writeText(plain)
    return true
  } catch {
    return false
  }
}

/** The HTML face of a code fence: the one shape every rich-text target reads. */
export function codeFenceHtml(source: string, language?: string): string {
  const escaped = source
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  const tag = /^[a-z0-9+#._-]+$/i.test(language ?? '') ? ` class="language-${language}"` : ''
  return `<pre><code${tag}>${escaped}</code></pre>`
}
