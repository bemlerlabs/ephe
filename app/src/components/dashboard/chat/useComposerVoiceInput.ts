import { useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import { transcribeAudio } from '@/lib/api'
import { toastBus } from '@/lib/toast'

/**
 * Voice input: record → /api/audio/transcribe (faster-whisper) → text into the
 * input. R18: hold to talk (press = record, release = stop) + tap toggle, level
 * meter via AnalyserNode, barge-in (ephe:stop-speech). Extracted from ChatInput.tsx.
 *
 * QD-008 fixed two defects the owner hit on the installed app: a tap-latched
 * recording could not be stopped by tapping again (pointerup was the only place
 * that cleared the latch), and the recorder demanded `audio/webm`, which the
 * WKWebView shell does not record — so nothing reached the transcriber there.
 */
const HOLD_MS = 300

/** Preference order; the first entry the engine can actually record wins. */
const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
  'audio/wav',
] as const

function pickMimeType(): string | undefined {
  const Recorder = typeof MediaRecorder === 'undefined' ? undefined : MediaRecorder
  if (!Recorder?.isTypeSupported) return undefined
  for (const type of MIME_CANDIDATES) {
    try {
      if (Recorder.isTypeSupported(type)) return type
    } catch {
      /* some engines throw on an unknown type instead of answering false */
    }
  }
  return undefined
}

export function useComposerVoiceInput({
  setMessage,
  textareaRef,
}: {
  setMessage: Dispatch<SetStateAction<string>>
  textareaRef: RefObject<HTMLTextAreaElement | null>
}) {
  const { t } = useTranslation()
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  // A start in flight (getUserMedia pending) and a stop that outran it both need
  // to be told apart from "nothing happening" — the session counter is what a
  // cancelled start compares against when its promise finally resolves.
  const sessionRef = useRef(0)
  const startingRef = useRef(false)
  const discardRef = useRef(false)
  const pressEndedRef = useRef<{ held: number } | null>(null)
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

  const releaseStream = () => {
    streamRef.current?.getTracks().forEach((tr) => tr.stop())
    streamRef.current = null
  }

  const stopLevelMeter = () => {
    cancelAnimationFrame(rafRef.current)
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    setMicLevel(0)
  }

  /** Stops — or, with `discard`, aborts — a recording that is running or still starting. */
  const stopVoiceRecording = (discard = false) => {
    discardRef.current = discard
    sessionRef.current += 1
    startingRef.current = false
    pressEndedRef.current = null
    stopLevelMeter()
    const rec = recorderRef.current
    // `state` is absent on the jsdom stand-in; only a live recorder may be stopped.
    if (rec && rec.state !== 'inactive') {
      rec.stop() // onstop releases the stream and settles the state
      return
    }
    recorderRef.current = null
    releaseStream()
    setRecording(false)
  }

  const startLevelMeter = (stream: MediaStream) => {
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
          const history = micLevelsRef.current
          history.copyWithin(0, 1) // in-place shift, no copy
          history[history.length - 1] = level
          setMicFrame((f) => f + 1)
        }
        rafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      // Analyser optional — recording works even without a level meter.
    }
  }

  const startRecording = async () => {
    const session = ++sessionRef.current
    startingRef.current = true
    try {
      // R18 barge-in: stop reading aloud as soon as the user starts recording.
      window.dispatchEvent(new CustomEvent('ephe:stop-speech'))
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (sessionRef.current !== session) {
        // Cancelled while the permission prompt was open.
        stream.getTracks().forEach((tr) => tr.stop())
        return
      }
      streamRef.current = stream
      const mime = pickMimeType()
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      startingRef.current = false
      recorderRef.current = rec
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      rec.onstop = async () => {
        if (recorderRef.current === rec) recorderRef.current = null
        releaseStream()
        setRecording(false)
        const discard = discardRef.current
        discardRef.current = false
        if (discard || chunks.length === 0) return
        const type = rec.mimeType || mime || 'audio/webm'
        setTranscribing(true)
        try {
          const text = await transcribeAudio(new Blob(chunks, { type }))
          if (!text) return
          if (text.startsWith('[Transkriptions-Fehler') || text.startsWith('[voice message')) {
            toastBus.error(text)
            return
          }
          setMessage((prev) => (prev ? `${prev} ${text}` : text))
          textareaRef.current?.focus()
        } catch (err) {
          toastBus.error(
            err instanceof Error && err.message ? err.message : t('chat.transcribeFailed'),
          )
        } finally {
          setTranscribing(false)
        }
      }
      rec.start()
      setRecording(true)
      startLevelMeter(stream)

      // A tap that ended before the microphone was ready still latches.
      const ended = pressEndedRef.current
      if (ended) {
        pressEndedRef.current = null
        if (ended.held >= HOLD_MS) stopVoiceRecording()
      }
    } catch (err) {
      startingRef.current = false
      // The stream may be live with the recorder unbuildable — the macOS
      // microphone indicator would stay on for the rest of the session.
      releaseStream()
      recorderRef.current = null
      setRecording(false)
      const name = err instanceof DOMException ? err.name : ''
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        toastBus.error(t('chat.micDenied'))
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        toastBus.error(t('chat.micMissing'))
      } else {
        toastBus.error(t('chat.micDenied'))
      }
    }
  }

  // R18 hold to talk: pointerdown starts, pointerup stops when held past the
  // threshold; a short tap latches, and any press while recording stops it.
  const onMicPointerDown = () => {
    if (recorderRef.current || startingRef.current) {
      stopVoiceRecording()
      return
    }
    pointerDownAtRef.current = Date.now()
    pressEndedRef.current = null
    void startRecording()
  }
  const onMicPointerUp = () => {
    if (!recorderRef.current && !startingRef.current) return
    const held = Date.now() - pointerDownAtRef.current
    if (held >= HOLD_MS) stopVoiceRecording()
    else pressEndedRef.current = { held }
  }

  // Escape aborts a running recording — the audio is dropped, not transcribed.
  const stopRef = useRef(stopVoiceRecording)
  useEffect(() => {
    stopRef.current = stopVoiceRecording
  })
  useEffect(() => {
    if (!recording) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      stopRef.current(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [recording])

  return { recording, transcribing, micFrame, micLevelsRef, onMicPointerDown, onMicPointerUp }
}
