/**
 * A prepared example handed from the settings surface to the chat.
 *
 * The composer belongs to the chat route, which mounts after the navigation. The
 * text waits here for that mount; the chat view opens a fresh session for it, so a
 * probe never lands in the transcript the user was reading.
 */
let pending: string | null = null

export function startDisposableChat(prompt: string): void {
  pending = prompt
  window.location.hash = '#/chat'
}

export function takeChatSeed(): string | null {
  const seed = pending
  pending = null
  return seed
}
