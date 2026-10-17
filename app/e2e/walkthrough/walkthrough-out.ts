/**
 * Where a walkthrough spec writes its captures.
 *
 * The dated record under docs/media/user-walkthrough-2026-10-12/ is tracked evidence:
 * FINDINGS.md and the per-spec notes cite its files by path. The specs wrote there on
 * every run, so a plain verification run rewrote tracked files and left the tree dirty.
 * Captures land in the scratch root below instead; the record is rewritten only when
 * EPHE_WALKTHROUGH_OUT names it.
 *
 *   EPHE_WALKTHROUGH_OUT  capture root, repo-relative or absolute; a spec writes into
 *                         <root>/<slug>/. Unset → app/.walkthrough-out/<slug>/.
 *
 * A fresh dated set is produced on purpose and its kept files are committed by hand:
 * see README.md beside this file.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))

/** The repo root: this file sits at <repo>/app/e2e/walkthrough/. */
export const REPO_ROOT = path.resolve(HERE, '..', '..', '..')

const SCRATCH_ROOT = path.join(REPO_ROOT, 'app', '.walkthrough-out')

/**
 * The capture directory of one spec, keyed by the slug its record directory uses.
 * Slug and record directory must match, because the dated set is the read-back the
 * findings cite.
 */
export function walkthroughOutDir(slug: string): string {
  const root = process.env.EPHE_WALKTHROUGH_OUT
  return path.join(root ? path.resolve(REPO_ROOT, root) : SCRATCH_ROOT, slug)
}
