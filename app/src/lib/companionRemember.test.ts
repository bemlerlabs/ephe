import { beforeEach, describe, expect, it } from 'vitest'
import { classifyShellCommand } from './companionCopilot'
import {
  canRememberShape,
  forgetShellShapes,
  rememberShellShape,
  rememberedShellVerbs,
} from './companionRemember'

describe('remember this command shape', () => {
  beforeEach(() => {
    window.localStorage.clear()
    forgetShellShapes()
  })

  it('remembers a plain verb and makes that verb auto-act', () => {
    expect(classifyShellCommand('jq . package.json')).toBe('warn_only')
    expect(rememberShellShape('jq . package.json')).toBe(true)
    expect(rememberedShellVerbs()).toContain('jq')
    expect(classifyShellCommand('jq . other.json', rememberedShellVerbs())).toBe('auto_act')
  })

  it('refuses to remember anything the fence blocks', () => {
    expect(rememberShellShape('rm -rf .')).toBe(false)
    expect(rememberShellShape('jq . a.json && rm b')).toBe(false)
    expect(rememberShellShape('cat ../secret')).toBe(false)
    expect(rememberedShellVerbs()).toHaveLength(0)
    expect(canRememberShape('npm test')).toBe(true)
  })

  it('is idempotent and survives a remount', () => {
    rememberShellShape('jq . a.json')
    rememberShellShape('jq . b.json')
    expect(rememberedShellVerbs()).toEqual(['jq'])
    expect(JSON.parse(window.localStorage.getItem('ephe.companion.rememberedShapes') ?? '[]')).toEqual(['jq'])
  })

  it('forgets everything on request', () => {
    rememberShellShape('jq . a.json')
    forgetShellShapes()
    expect(rememberedShellVerbs()).toHaveLength(0)
  })
})
