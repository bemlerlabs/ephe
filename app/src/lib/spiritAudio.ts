/**
 * The companion's voice: a tiny Web Audio synth, no audio files.
 *
 * Two gestures are all the product needs — the wing flutter of a click-flight and
 * a D-pentatonic bell when the spark bursts. Both are silent unless the user keeps
 * `appearance.companion_sound`, keeps animations on, and has not asked the system
 * for reduced motion; a browser without Web Audio is a no-op, not an error.
 */
import { deepBool } from '@/lib/deepSettings'

const PENTATONIC = [587.33, 739.99, 880.0, 987.77, 1174.66] // D5 F#5 A5 B5 D6

let context: AudioContext | null = null
let noise: AudioBuffer | null = null
let chimeStep = 0

export function spiritAudioAllowed(): boolean {
  if (typeof window === 'undefined') return false
  if (!deepBool('appearance.companion_sound', true)) return false
  if (!deepBool('appearance.animations_enabled', true)) return false
  try {
    return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return true
  }
}

function audio(): AudioContext | null {
  if (!spiritAudioAllowed()) return null
  if (!context) {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return null
    try {
      context = new Ctor()
    } catch {
      return null
    }
  }
  if (context.state === 'suspended') void context.resume().catch(() => undefined)
  return context
}

function noiseBuffer(ctx: AudioContext): AudioBuffer {
  if (noise) return noise
  const length = Math.floor(ctx.sampleRate * 0.5)
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < length; i += 1) data[i] = Math.random() * 2 - 1
  noise = buffer
  return buffer
}

function panned(ctx: AudioContext, pan: number): StereoPannerNode | null {
  if (!ctx.createStereoPanner) return null
  const node = ctx.createStereoPanner()
  node.pan.value = Math.max(-1, Math.min(1, pan))
  return node
}

/** A warm wing flutter for a click-flight; `pan` -1..1 places it left to right. */
export function playWingWhoosh(pan = 0, gain = 0.05): void {
  const ctx = audio()
  if (!ctx) return
  const now = ctx.currentTime
  const source = ctx.createBufferSource()
  source.buffer = noiseBuffer(ctx)
  const band = ctx.createBiquadFilter()
  band.type = 'bandpass'
  band.Q.value = 1.4
  band.frequency.setValueAtTime(520, now)
  band.frequency.exponentialRampToValueAtTime(1450, now + 0.16)
  band.frequency.exponentialRampToValueAtTime(620, now + 0.36)
  const envelope = ctx.createGain()
  envelope.gain.setValueAtTime(0.0001, now)
  envelope.gain.exponentialRampToValueAtTime(gain, now + 0.035)
  envelope.gain.exponentialRampToValueAtTime(0.0001, now + 0.38)
  const panner = panned(ctx, pan)
  source.connect(band)
  band.connect(envelope)
  if (panner) {
    envelope.connect(panner)
    panner.connect(ctx.destination)
  } else {
    envelope.connect(ctx.destination)
  }
  source.start(now)
  source.stop(now + 0.4)
}

/** One crystal bell from the D-pentatonic; index 0..4 or the next note in sequence. */
export function playSparkChime(index?: number, when = 0, gain = 0.075): void {
  const ctx = audio()
  if (!ctx) return
  const note = PENTATONIC[(index ?? chimeStep++) % PENTATONIC.length] as number
  const start = ctx.currentTime + when
  const panner = panned(ctx, ((chimeStep % 5) / 2 - 1) * 0.45)
  const tail = ctx.createGain()
  tail.gain.setValueAtTime(0.0001, start)
  tail.gain.exponentialRampToValueAtTime(gain, start + 0.012)
  tail.gain.exponentialRampToValueAtTime(0.0001, start + 1.15)
  if (panner) {
    tail.connect(panner)
    panner.connect(ctx.destination)
  } else {
    tail.connect(ctx.destination)
  }
  for (const [ratio, level] of [
    [1, 1],
    [2.01, 0.24],
    [3.02, 0.08],
  ] as const) {
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = note * ratio
    const voice = ctx.createGain()
    voice.gain.value = level
    osc.connect(voice)
    voice.connect(tail)
    osc.start(start)
    osc.stop(start + 1.2)
  }
}

/** A four-note answer for a burst, spaced so it reads as one shimmer. */
export function playSparkBurst(count = 4): void {
  if (!spiritAudioAllowed()) return
  for (let i = 0; i < count; i += 1) playSparkChime(i, i * 0.07, 0.055)
}
