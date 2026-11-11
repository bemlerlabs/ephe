/**
 * The landing page's claims, checked against the checkout.
 *
 * A marketing page is where prose outlives its source. Every row names a file; every
 * figure names the paper that measured it. This file reads both, so a renamed path, a
 * drifted installer command or an edited number fails here rather than on the page.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  COMPARISON_ROWS,
  IMPORT_ROWS,
  INSTALL_COMMAND,
  INSTALL_VERSION,
  STUDIES,
} from './landingFacts'
import en from '@/locales/en.json'
import de from '@/locales/de.json'

/** The checkout root: vitest runs at the app directory (or the repository root). */
function repoRoot(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), '..')]) {
    if (existsSync(resolve(base, 'README.md')) && existsSync(resolve(base, 'app'))) return base
  }
  throw new Error(`repository root not found above ${process.cwd()}`)
}
const ROOT = repoRoot()
const read = (rel: string) => readFileSync(resolve(ROOT, rel), 'utf8')

type Bundle = Record<string, unknown>
const bundles: Array<[string, Bundle]> = [
  ['en', en as unknown as Bundle],
  ['de', de as unknown as Bundle],
]

function leaf(bundle: Bundle, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      bundle,
    )
}

describe('the landing page states only what the checkout holds', () => {
  it('proves every comparison row with a file that exists', () => {
    for (const row of COMPARISON_ROWS) {
      expect(existsSync(resolve(ROOT, row.proofPath)), row.proofPath).toBe(true)
    }
    expect(COMPARISON_ROWS.map((row) => row.id)).toEqual([
      'engine',
      'account',
      'license',
      'plugins',
      'context',
      'verification',
    ])
  })

  it('has a sentence for every row and every import artifact, in both languages', () => {
    const keys = [
      ...COMPARISON_ROWS.flatMap((row) => [row.questionKey, row.answerKey]),
      ...IMPORT_ROWS.flatMap((row) => [row.artifactKey, row.landsKey]),
    ]
    for (const [language, bundle] of bundles) {
      for (const key of keys) {
        expect(typeof leaf(bundle, key), `${language} ${key}`).toBe('string')
      }
    }
  })

  it('prints the installer command the README carries', () => {
    const readme = read('README.md')
    expect(readme).toContain(INSTALL_COMMAND)
    expect(INSTALL_COMMAND).toContain(`/v${INSTALL_VERSION}/install.sh`)
    expect(existsSync(resolve(ROOT, 'install.sh'))).toBe(true)
    expect(existsSync(resolve(ROOT, 'install.ps1'))).toBe(true)
  })

  it('keeps the two studies the numbers came from', () => {
    expect(STUDIES.agentsMd.href).toBe('https://arxiv.org/abs/2601.20404')
    expect(STUDIES.realm.href).toBe('https://aclanthology.org/2026.realm-1.5/')
    expect(STUDIES.agentsMd.pullRequests).toBe(124)
    expect(STUDIES.realm.runs).toBe(288)
  })

  it('prints the figures the papers report, in both languages', () => {
    const english = leaf(en as unknown as Bundle, 'landing.proof')
    const german = leaf(de as unknown as Bundle, 'landing.proof')
    if (typeof english !== 'object' || typeof german !== 'object') {
      throw new Error('landing.proof is not an object')
    }
    const [enProof, deProof] = [english as unknown, german as unknown] as [
      Record<string, string>,
      Record<string, string>,
    ]
    const runtime = STUDIES.agentsMd.runtimePct.toFixed(1)
    const tokens = STUDIES.agentsMd.tokensPct.toFixed(1)
    const [low, high] = STUDIES.realm.equivalencePp
    const bound = `${low}–${high}`

    expect(enProof.agentsMdBody).toContain(`${runtime}%`)
    expect(enProof.agentsMdBody).toContain(`${tokens}%`)
    expect(enProof.agentsMdBody).toContain(String(STUDIES.agentsMd.pullRequests))
    expect(enProof.agentsMdBody).toContain(String(STUDIES.agentsMd.repositories))
    expect(enProof.realmValue).toContain(bound)
    expect(enProof.realmBody).toContain(bound)
    expect(enProof.realmBody).toContain(String(STUDIES.realm.tasks))
    expect(enProof.realmBody).toContain(String(STUDIES.realm.runs))

    expect(deProof.agentsMdBody).toContain(`${runtime.replace('.', ',')} %`)
    expect(deProof.agentsMdBody).toContain(`${tokens.replace('.', ',')} %`)
    expect(deProof.agentsMdBody).toContain(String(STUDIES.agentsMd.pullRequests))
    expect(deProof.realmBody).toContain(bound)
  })
})
