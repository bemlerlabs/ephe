/**
 * The paper rustle of the unfold, synthesised rather than shipped as a sample.
 *
 * One short noise burst through a band-pass that opens as it decays: that is the
 * shape of a sheet folding, and it costs no asset, no licence and no decode. Silent
 * where the reader asked for reduced motion or where the browser has no audio — the
 * unfold itself still plays.
 */
let context: AudioContext | null = null

function preferredReduced(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

export function paperRustle(seconds = 0.45): void {
  if (typeof window === 'undefined' || preferredReduced()) return
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return
  try {
    context ??= new Ctor()
    const ctx = context
    if (ctx.state === 'suspended') void ctx.resume()
    const frames = Math.round(ctx.sampleRate * seconds)
    const buffer = ctx.createBuffer(1, frames, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < frames; i += 1) {
      const t = i / frames
      // A fold is three small creases, not one hiss: the envelope steps down.
      const envelope = Math.exp(-3.2 * t) * (0.65 + 0.35 * Math.sin(t * 46))
      data[i] = (Math.random() * 2 - 1) * envelope
    }
    const source = ctx.createBufferSource()
    source.buffer = buffer
    const band = ctx.createBiquadFilter()
    band.type = 'bandpass'
    band.frequency.setValueAtTime(2400, ctx.currentTime)
    band.frequency.exponentialRampToValueAtTime(900, ctx.currentTime + seconds)
    band.Q.setValueAtTime(0.8, ctx.currentTime)
    const gain = ctx.createGain()
    gain.gain.setValueAtTime(0.0001, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.04)
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + seconds)
    source.connect(band).connect(gain).connect(ctx.destination)
    source.start()
    source.stop(ctx.currentTime + seconds)
  } catch {
    // A blocked audio context is not a failure of the unfold.
  }
}
