/**
 * IntroFilm — the five camera setups.
 *
 * GIVEN a timestamp on the film's clock
 * WHEN  the shot is read
 * THEN  it names the wide establishing shot, the low stream track, the close-up,
 *       the vortex or the macro portrait, cut at the film's own boundaries.
 */
import { describe, it, expect } from 'vitest'
import { shotAt } from './introFilmTimeline'

describe('IntroFilm shots', () => {
  it.each([
    [0, 1],
    [2199, 1],
    [2200, 2],
    [5199, 2],
    [5200, 3],
    [6599, 3],
    [6600, 4],
    [9399, 4],
    [9400, 5],
    [12_800, 5],
  ])('at %i ms the film is in shot %i', (at, shot) => {
    expect(shotAt(at)).toBe(shot)
  })
})
