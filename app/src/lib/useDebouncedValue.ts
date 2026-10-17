import { useEffect, useState } from 'react'

/**
 * The value as it stands once typing stops.
 *
 * Both search fields used to sit directly in their fetch effect, so every letter of
 * a word cost one round trip: measured on the memory route, 6 keystrokes of `Kaffee`
 * answered with 6 `GET /api/memory/search`, each one a vector search over the whole
 * store on the engine's clock. The hold is by value, not by event, so a paste or a
 * clear button lands on the same path as a typed letter.
 */
export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [held, setHeld] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setHeld(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return held
}
