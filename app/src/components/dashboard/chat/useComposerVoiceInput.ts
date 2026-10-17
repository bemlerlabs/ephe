import { useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import { transcribeAudio } from '@/lib/api'
import { toastBus } from '@/lib/toast'

/**
 * Voice input: record → /api/audio/transcribe (faster-whisper) → text into the
 * input. R18: hold to talk (press = record, release = stop) + tap toggle
 * (< 250 ms), level meter via AnalyserNode, barge-in (ephe:stop-speech).
 * Extracted from ChatInput.tsx.
 */
export function useComposerVoiceInput({
  setMessage,
  textareaRef,
}: {
  setMessage: Dispatch<SetStateAction<string>>
  textareaRef: RefObject<HTMLTextAreaElement | null>
}) {
  const { t } = useTranslation()
  const recorderRef = useRef<MediaRecorder | null>(null)
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [, setMicLevel] = useState(0)
  // P2-2: rolling history as a preallocated Float32Array + in-place ring —
  // no spread copy per tick; a counter state triggers the ~12fps render.
  const micLevelsRef = useRef<Float32Array>(new Float32Array(20))
  const [micFrame, setMicFrame] = useState(0)
  const levelTickRef = useRef(0)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number>(0)
  const pointerDownAtRef = useRef(0)
  const latchedRef = useRef(false)

  const stopVoiceRecording = () => {
    recorderRef.current?.stop()
    cancelAnimationFrame(rafRef.current)
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    setMicLevel(0)
  }

  const toggleVoice = async () => {
    if (recorderRef.current) {
      stopVoiceRecording()
      return
    }
    try {
      // R18 barge-in: stop reading aloud as soon as the user starts recording.
      window.dispatchEvent(new CustomEvent('ephe:stop-speech'))
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      recorderRef.current = rec
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data)
      rec.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop())
        recorderRef.current = null
        setRecording(false)
        setTranscribing(true)
        try {
          const text = await transcribeAudio(new Blob(chunks, { type: 'audio/webm' }))
          if (text && !text.startsWith('[Transkriptions-Fehler')) {
            setMessage((prev) => (prev ? `${prev} ${text}` : text))
            textareaRef.current?.focus()
          }
        } finally {
          setTranscribing(false)
        }
      }
      rec.start()
      setRecording(true)

      // Level meter (waveform stand-in: live RMS level)
      try {
        const ctx = new AudioContext()
        audioCtxRef.current = ctx
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        ctx.createMediaStreamSource(stream).connect(analyser)
        const buf = new Uint8Array(analyser.frequencyBinCount)
        const tick = () => {
          analyser.getByteTimeDomainData(buf)
          let sum = 0
          for (let i = 0; i < buf.length; i++) {
            const v = ((buf[i] ?? 128) - 128) / 128
            sum += v * v
          }
          const level = Math.min(1, Math.sqrt(sum / buf.length) * 3)
          setMicLevel(level)
          // R18 waveform: rolling history (~12 fps) — level trace as a bar row
          levelTickRef.current += 1
          if (levelTickRef.current % 5 === 0) {
            const buf = micLevelsRef.current
            buf.copyWithin(0, 1) // in-place shift, no copy
            buf[buf.length - 1] = level
            setMicFrame((f) => f + 1)
          }
          rafRef.current = requestAnimationFrame(tick)
        }
        tick()
      } catch {
        // Analyser optional — recording works even without a level meter.
      }
    } catch (err) {
      // P1-10: a denied/missing microphone was silent until now — the button just
      // disappeared and the user had no idea why. Give an honest hint.
      const name = err instanceof DOMException ? err.name : ''
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        toastBus.error(t('chat.micDenied'))
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        toastBus.error(t('chat.micMissing'))
      }
      setRecording(false)
    }
  }

  // R18 hold to talk: pointerdown starts, pointerup stops when held > 250 ms;
  // a short tap = latched toggle (the old click convenience).
  const onMicPointerDown = () => {
    pointerDownAtRef.current = Date.now()
    if (recorderRef.current) return // latched → pointerup must not stop it again
    void toggleVoice()
  }
  const onMicPointerUp = () => {
    const held = Date.now() - pointerDownAtRef.current
    if (recorderRef.current && held > 250 && !latchedRef.current) {
      stopVoiceRecording()
      latchedRef.current = false
    } else if (!recorderRef.current) {
      latchedRef.current = false
    } else {
      latchedRef.current = true // short tap: recording keeps running until the next tap
      if (recorderRef.current && held > 250) return
    }
  }

  return { recording, transcribing, micFrame, micLevelsRef, onMicPointerDown, onMicPointerUp }
}
