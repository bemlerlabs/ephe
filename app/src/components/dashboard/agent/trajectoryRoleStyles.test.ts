import { describe, expect, it } from 'vitest'
import { trajectoryRoleTextClass, trajectoryRoleMarkerClass } from './trajectoryRoleStyles'

describe('trajectoryRoleTextClass', () => {
  it('mappt Reasoning-Rollen auf die Violett-Klasse', () => {
    expect(trajectoryRoleTextClass('reasoning')).toBe('text-trajectory-reasoning')
    expect(trajectoryRoleTextClass('thinking_start')).toBe('text-trajectory-reasoning')
  })

  it('mappt Message/User auf die Assistant-/User-Klasse', () => {
    expect(trajectoryRoleTextClass('message')).toBe('text-trajectory-assistant')
    expect(trajectoryRoleTextClass('user')).toBe('text-trajectory-user')
  })

  it('mappt Tool-Rollen auf Amber-/Cyan-Klasse', () => {
    expect(trajectoryRoleTextClass('tool_call')).toBe('text-trajectory-tool-call')
    expect(trajectoryRoleTextClass('tool_result')).toBe('text-trajectory-tool-result')
  })

  it('mappt usage auf die subtile Text-Klasse', () => {
    expect(trajectoryRoleTextClass('usage')).toBe('text-mist-dim')
  })

  it('mappt die Backend-Live-Typen (activity/tool_start/tool_done) auf Rollenfarben', () => {
    expect(trajectoryRoleTextClass('activity')).toBe('text-trajectory-assistant')
    expect(trajectoryRoleTextClass('tool_start')).toBe('text-trajectory-tool-call')
    expect(trajectoryRoleTextClass('tool_done')).toBe('text-trajectory-tool-call')
    expect(trajectoryRoleTextClass('reflect')).toBe('text-trajectory-reasoning')
  })

  it('ist case-insensitive — der Backend speichert Typen UPPERCASE', () => {
    expect(trajectoryRoleTextClass('THINKING_START')).toBe('text-trajectory-reasoning')
    expect(trajectoryRoleTextClass('ACTIVITY')).toBe('text-trajectory-assistant')
    expect(trajectoryRoleTextClass('TOOL_START')).toBe('text-trajectory-tool-call')
    expect(trajectoryRoleTextClass('TOOL_RESULT')).toBe('text-trajectory-tool-result')
  })

  it('liefert den text-ui-sm-Fallback fuer unbekannte Types', () => {
    expect(trajectoryRoleTextClass('nope')).toBe('text-ui-sm')
    expect(trajectoryRoleTextClass('')).toBe('text-ui-sm')
  })
})

describe('trajectoryRoleMarkerClass (N4′ — step-type→Farb-Map als Rand-Marke)', () => {
  it('mappt Rollen auf die border-l-Klassen derselben Farbserie', () => {
    expect(trajectoryRoleMarkerClass('reasoning')).toBe('border-l-trajectory-reasoning')
    expect(trajectoryRoleMarkerClass('message')).toBe('border-l-trajectory-assistant')
    expect(trajectoryRoleMarkerClass('user')).toBe('border-l-trajectory-user')
    expect(trajectoryRoleMarkerClass('tool_call')).toBe('border-l-trajectory-tool-call')
    expect(trajectoryRoleMarkerClass('tool_result')).toBe('border-l-trajectory-tool-result')
    expect(trajectoryRoleMarkerClass('tool_start')).toBe('border-l-trajectory-tool-call')
  })

  it('ist case-insensitive und liefert randlosen Fallback fuer Unbekanntes', () => {
    expect(trajectoryRoleMarkerClass('TOOL_RESULT')).toBe('border-l-trajectory-tool-result')
    expect(trajectoryRoleMarkerClass('nope')).toBe('border-l-transparent')
    expect(trajectoryRoleMarkerClass('')).toBe('border-l-transparent')
  })
})
