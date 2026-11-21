import { describe, expect, it } from 'vitest'
import { classifyShellCommand } from './companionCopilot'
import { canRememberShape } from './companionRemember'
describe('read-only workspace inspection (QD-008)', () => {
  it.each([
    'ls -1 .',
    'ls -la',
    'cat README.md',
    'head -n 20 notes.md',
    'tail -5 log.txt',
    'wc -l notes.md',
    'stat package.json',
    'du -sh .',
    'pwd',
    'which git',
    'file a.png',
    'rg todo',
    'grep -i error log.txt',
    'find . -maxdepth 2',
    'find . -type f -name "*.md"',
  ])('reads %j as safe inspection', (command) => {
    expect(classifyShellCommand(command)).toBe('auto_act')
  })

  it.each([
    'find . -delete',
    'find . -exec rm {} ;',
    'find . -execdir sh -c id ;',
    'find . -fprint out.txt',
    'sed -i "" s/a/b/ notes.md',
    'sed -ni 1p notes.md',
    'sed --in-place s/a/b/ notes.md',
    'ls /etc',
    'cat ~/.ssh/id_rsa',
    'cat ../outside.txt',
    'grep error . > hits.txt',
    'ls | wc -l',
  ])('still refuses %j', (command) => {
    expect(classifyShellCommand(command)).toBe('warn_only')
  })
})

describe('user-taught shapes (QD-008)', () => {
  it('offers to remember a plain verb and never a forbidden line', () => {
    expect(canRememberShape('jq . package.json')).toBe(true)
    expect(canRememberShape('rm -rf .')).toBe(false)
    expect(canRememberShape('jq . a.json && rm b')).toBe(false)
    expect(canRememberShape('./run.sh')).toBe(false)
  })

  it('approves a remembered verb, and the fence still runs per command', () => {
    expect(classifyShellCommand('jq . package.json')).toBe('warn_only')
    expect(classifyShellCommand('jq . package.json', ['jq'])).toBe('auto_act')
    expect(classifyShellCommand('jq . a.json && rm b', ['jq'])).toBe('warn_only')
    expect(classifyShellCommand('jq . a.json > out.json', ['jq'])).toBe('warn_only')
  })
})
