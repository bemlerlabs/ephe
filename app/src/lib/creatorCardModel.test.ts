/**
 * #28 — the model behind the creator card.
 *
 * The card is allowed to state one thing about a staged bundle: what one of the four
 * creator calls answered. Every field below is traced to a payload in
 * `core/tools/creator_tools.py`, and the tests pin the two shapes the card must not
 * confuse: a bundle that is not verified yet, and a bundle whose install was refused.
 */
import { describe, it, expect } from 'vitest'
import { CREATOR_TOOLS, creatorModelFor } from './creatorCardModel'

const json = (o: unknown) => JSON.stringify(o)

const SCAFFOLD = json({
  bundle: '/var/folders/ephe/creator/plugins/timer',
  name: 'timer',
  version: '0.1.0',
  license: 'LicenseRef-proprietary',
  publisher: 'Independent',
  files: ['ephe-plugin.json', 'ui/app.css', 'ui/app.js', 'ui/index.html'],
  next: 'write_plugin_source(bundle, path, content), then verify_plugin_bundle(bundle)',
})

const call = (name: string, args: Record<string, unknown>, result?: string, status = 'done') =>
  ({ id: name + status, name, args, result, status }) as const

describe('creatorCardModel (issue #28)', () => {
  it('names the four calls the creator card reads', () => {
    expect([...CREATOR_TOOLS].sort()).toEqual([
      'create_plugin_scaffold',
      'install_plugin_bundle',
      'verify_plugin_bundle',
      'write_plugin_source',
    ])
  })

  it('takes the bundle name and its first files from the scaffold answer', () => {
    const m = creatorModelFor([call('create_plugin_scaffold', { name: 'timer' }, SCAFFOLD)])
    expect(m).not.toBeNull()
    expect(m?.name).toBe('timer')
    expect(m?.version).toBe('0.1.0')
    expect(m?.publisher).toBe('Independent')
    expect(m?.license).toBe('LicenseRef-proprietary')
    expect(m?.files).toEqual(['ephe-plugin.json', 'ui/app.css', 'ui/app.js', 'ui/index.html'])
    expect(m?.staged).toBe(true)
    expect(m?.verified).toBe(false)
    expect(m?.installed).toBe(false)
  })

  it('adds a file the source tool reports and keeps one entry per path', () => {
    const m = creatorModelFor([
      call('create_plugin_scaffold', { name: 'timer' }, SCAFFOLD),
      call(
        'write_plugin_source',
        { bundle: 'timer', path: 'ui/app.js' },
        json({ bundle: '/x/timer', path: 'ui/app.js', bytes: 120, created: false, next: 'v' }),
      ),
      call(
        'write_plugin_source',
        { bundle: 'timer', path: 'data/notes.md' },
        json({ bundle: '/x/timer', path: 'data/notes.md', bytes: 12, created: true, next: 'v' }),
      ),
    ])
    expect(m?.files).toEqual([
      'ephe-plugin.json',
      'ui/app.css',
      'ui/app.js',
      'ui/index.html',
      'data/notes.md',
    ])
    expect(m?.writes).toBe(2)
  })

  it('reads a verification as the verdict the answer carries', () => {
    const ok = call(
      'verify_plugin_bundle',
      { bundle: 'timer' },
      json({
        ok: true,
        bundle: '/x/timer',
        sha256: 'a'.repeat(64),
        name: 'timer',
        version: '0.1.0',
        tools: [],
        next: 'install_plugin_bundle(bundle)',
      }),
    )
    const bad = call(
      'verify_plugin_bundle',
      { bundle: 'timer' },
      json({
        ok: false,
        error: 'manifest_invalid',
        bundle: '/x/timer',
        sha256: 'b'.repeat(64),
        problems: ["tool 'run': entry file is missing"],
        next: 'ship the file each entry names, inside the bundle',
      }),
    )
    expect(creatorModelFor([bad, ok])?.verified).toBe(true)
    expect(creatorModelFor([bad, ok])?.problems).toEqual([])
    expect(creatorModelFor([ok, bad])?.verified).toBe(false)
    expect(creatorModelFor([ok, bad])?.error).toBe('manifest_invalid')
    expect(creatorModelFor([ok, bad])?.problems).toEqual(["tool 'run': entry file is missing"])
    expect(creatorModelFor([ok, bad])?.sha256).toBe('b'.repeat(64))
  })

  it('marks a bundle installed only when the install answer says so', () => {
    const install = call(
      'install_plugin_bundle',
      { bundle: 'timer' },
      json({
        status: 'installed',
        name: 'timer',
        version: '0.1.0',
        trust: 'local',
        sha256: 'c'.repeat(64),
        bundle: '/plugins/timer',
        enabled: true,
        next: 'the Extensions surface holds the switch and the mount for this bundle',
      }),
    )
    const m = creatorModelFor([
      call('create_plugin_scaffold', { name: 'timer' }, SCAFFOLD),
      install,
    ])
    expect(m?.installed).toBe(true)
    expect(m?.enabled).toBe(true)
    expect(m?.trust).toBe('local')
    expect(m?.sha256).toBe('c'.repeat(64))
  })

  it('keeps a refused install out of the installed state and names the refusal', () => {
    const m = creatorModelFor([
      call(
        'install_plugin_bundle',
        { bundle: 'timer' },
        json({
          error: 'install_refused',
          bundle: '/x/timer',
          detail: { status: 'rejected', reason: 'hash mismatch' },
          next: 'the installed bundle is unchanged; fix the staged bytes and verify again',
        }),
      ),
    ])
    expect(m?.installed).toBe(false)
    expect(m?.error).toBe('install_refused')
  })

  it('counts a call that has not answered without claiming from it', () => {
    const m = creatorModelFor([
      call('create_plugin_scaffold', { name: 'timer' }, SCAFFOLD),
      call('write_plugin_source', { bundle: 'timer', path: 'ui/app.js' }, undefined, 'pending'),
    ])
    expect(m?.pending).toBe(1)
    expect(m?.writes).toBe(0)
    expect(m?.files).toHaveLength(4)
  })

  it('names the bundle from the call when no answer carries a name', () => {
    const m = creatorModelFor([
      call(
        'create_plugin_scaffold',
        { name: 'timer' },
        json({ error: 'invalid_bundle_name', detail: 'a bundle name is one folder name' }),
      ),
    ])
    expect(m?.name).toBe('timer')
    expect(m?.staged).toBe(false)
    expect(m?.error).toBe('invalid_bundle_name')
  })

  it('claims nothing from a result that is not one of the answers', () => {
    const m = creatorModelFor([
      call('create_plugin_scaffold', { name: 'timer' }, 'Traceback (most recent call last):'),
    ])
    expect(m?.staged).toBe(false)
    expect(m?.files).toEqual([])
    expect(m?.name).toBe('timer')
  })

  it('returns null when the turn holds no creator call', () => {
    expect(
      creatorModelFor([call('edit_file', { path: 'a.ts' }, '--- a.ts\n+++ a.ts\n@@\n+x\n')]),
    ).toBeNull()
    expect(creatorModelFor([])).toBeNull()
  })
})
