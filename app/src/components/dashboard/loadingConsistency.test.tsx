import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

/** WD-32 — loading-skeleton consistency across the dashboard surfaces.
 *
 *  Loading was drawn six ways: a colourless 12px spinner in the file tree, a
 *  half-opacity brand ring in the settings, a bare text line in five panels, a
 *  full brand ring on the data pages. This scan holds the single treatment in
 *  place — every surface draws its loading placeholder through `LoadingRow`, and
 *  none hand-rolls its own spinner beside a label.
 *
 *  Read from the config root, as ArtifactsPage.finish.test.ts does — jsdom hands
 *  out a non-file import.meta.url, so the URL form does not resolve. */
const SRC = (rel: string) => readFileSync(`src/${rel}`, 'utf-8')

const SURFACES = [
  'pages/ArtifactsPage.tsx',
  'pages/DiscoverPage.tsx',
  'pages/MemoryPage.tsx',
  'components/dashboard/artifacts/detail.tsx',
  'components/dashboard/artifacts/preview.tsx',
  'components/dashboard/artifacts/provenance.tsx',
  'components/dashboard/agent/filesTab.tsx',
  'components/dashboard/agent/filePreview.tsx',
  'components/dashboard/agent/readerView.tsx',
  'components/dashboard/agent/subagentsDetail.tsx',
  'components/dashboard/agent/tabsMemory.tsx',
  'components/dashboard/agent/reviewTab.tsx',
  'components/dashboard/settings/model/sections-voice.tsx',
  'components/dashboard/settings/model/sections-network.tsx',
  'components/dashboard/settings/model/sections-code-exec.tsx',
  'components/dashboard/settings/model/sections-plugins.tsx',
  'components/dashboard/settings/model/sections-tasks.tsx',
]

// sections-mcp is not a surface: after its catalog moved to Discover the panel
// has no placeholder left to draw, only the inline button spinners (health
// check, save) that a momentary action needs.
describe('WD-32 — the dashboard loads the same way everywhere', () => {
  it.each(SURFACES)('%s routes its loading placeholder through LoadingRow', (rel) => {
    const src = SRC(rel)
    expect(src).toContain('LoadingRow')
    expect(src).toContain('@/components/ui')
  })

  it.each(SURFACES)('%s no longer hand-rolls a spinner', (rel) => {
    expect(SRC(rel)).not.toContain('animate-spin')
  })

  it('draws the one spinner from the shared primitive', () => {
    const src = SRC('components/ui/LoadingRow.tsx')
    expect(src).toContain('animate-spin text-brand')
    expect(src).toContain('motion-reduce:animate-none')
    expect(src).toContain('aria-hidden="true"')
  })
})
