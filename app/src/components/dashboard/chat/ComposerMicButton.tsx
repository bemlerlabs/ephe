import { Mic } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RefObject } from 'react'

/**
 * R18 voice button: waveform ring while recording, hold-to-talk pointer pair,
 * disabled while transcribing. Extracted from ChatInput.tsx — the recording
 * state lives in chat/useComposerVoiceInput.
 */
export default function ComposerMicButton({
  recording,
  transcribing,
  micFrame,
  micLevelsRef,
  onPointerDown,
  onPointerUp,
}: {
  recording: boolean
  transcribing: boolean
  micFrame: number
  micLevelsRef: RefObject<Float32Array>
  onPointerDown: () => void
  onPointerUp: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="relative flex items-center shrink-0">
      {recording && (
        <div
          className="absolute -top-2 left-1/2 -translate-x-1/2 flex items-end gap-[2px] h-4 w-24"
          aria-hidden
          data-testid="mic-waveform"
          data-frame={micFrame}
        >
          {Array.from(micLevelsRef.current).map((lvl, i) => (
            <div
              key={i}
              className={`w-[3px] rounded-sm ${lvl > 0.6 ? 'bg-status-danger' : 'bg-status-success/70'}`}
              style={{ height: `${Math.max(8, Math.round(lvl * 100))}%` }}
            />
          ))}
        </div>
      )}
      <button
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        disabled={transcribing}
        aria-label={recording ? t('chat.stopRecording') : t('chat.voiceInput')}
        aria-pressed={recording}
        title={
          transcribing
            ? t('chat.transcribing')
            : recording
              ? t('chat.stopRecording')
              : t('chat.holdToTalk')
        }
        className={`p-2.5 rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 max-lg:min-w-11 max-lg:min-h-11 ${
          recording
            ? 'bg-status-danger/20 text-status-danger'
            : 'hover:bg-brand/10 text-ink-soft hover:text-brand'
        }`}
      >
        <Mic className="h-4 w-4" />
      </button>
    </div>
  )
}
