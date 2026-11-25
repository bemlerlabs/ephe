/**
 * Where a walkthrough spec writes its captures.
 *
 * Captures are run output, not tree content: nothing from a walkthrough run is
 * committed, and no spec or document cites a run's files as evidence. The specs
 * once wrote into a dated set under docs/media/ on every run, which rewrote
 * tracked files and left the tree dirty; captures land in the scratch root
 * below instead, and a dated set exists only where EPHE_WALKTHROUGH_OUT points it.
 *
 *   EPHE_WALKTHROUGH_OUT  capture root, repo-relative or absolute; a spec writes into
 *                         <root>/<slug>/. Unset → app/.walkthrough-out/<slug>/.
 *
 * A fresh dated set is produced on purpose, read by whoever ran it: see README.md
 * beside this file.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))

/** The repo root: this file sits at <repo>/app/e2e/walkthrough/. */
export const REPO_ROOT = path.resolve(HERE, '..', '..', '..')

const SCRATCH_ROOT = path.join(REPO_ROOT, 'app', '.walkthrough-out')

/**
 * The capture directory of one spec, keyed by the slug its directory uses.
 * Slug and directory name must match, because a run is read back by slug.
 */
export function walkthroughOutDir(slug: string): string {
  const root = process.env.EPHE_WALKTHROUGH_OUT
  return path.join(root ? path.resolve(REPO_ROOT, root) : SCRATCH_ROOT, slug)
}
