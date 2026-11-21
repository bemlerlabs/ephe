import { m } from 'framer-motion'
import { Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatStore } from '@/store/chatStore'
import { useMediaQuery } from '@/hooks/useMediaQuery'

export default function TypingIndicator() {
  const { t } = useTranslation()
  const { isTyping } = useChatStore()
  // R54: reduced-motion policy — no pulse, static indicator only.
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')

  if (!isTyping) return null

  return (
    <m.div
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? undefined : { opacity: 0, y: 10 }}
      role="status"
      className="flex items-center gap-3 p-4"
    >
      <div className="w-8 h-8 rounded-full glass-control flex items-center justify-center forest-glow-subtle">
        <Sparkles className="h-4 w-4 text-brand" aria-hidden="true" />
      </div>
      <div className="flex items-center gap-1.5" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <m.div
            key={i}
            className="w-2 h-2 rounded-full bg-brand"
            animate={reduced ? undefined : { scale: [0.8, 1.2, 0.8] }}
            transition={{
              duration: 1,
              repeat: reduced ? 0 : Infinity,
              delay: i * 0.2,
              ease: 'easeInOut',
            }}
          />
        ))}
      </div>
      <span className="text-ui-sm text-ink-faint">{t('chat.thinkingNow')}</span>
    </m.div>
  )
}
