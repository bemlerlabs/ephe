import { useChatStore } from '@/store/chatStore'

/** Thinking-chip key: 'On' once the session has a thinking block with an end stamp. */
export function useThinkingChipKey(): string {
  const st = useChatStore() as unknown as {
    sessions?: Array<{
      id: string
      messages?: Array<{ thinking?: { end?: number | null } | null }>
    }>
    activeSessionId?: string | null
    currentSession?: { messages?: Array<{ thinking?: { end?: number | null } | null }> } | null
  }
  const sess =
    st.sessions?.find((x) => x.id === st.activeSessionId) ?? st.currentSession ?? undefined
  return sess?.messages?.some((mm) => mm.thinking?.end != null)
    ? 'chat.thinkingOn'
    : 'chat.thinkingOff'
}
