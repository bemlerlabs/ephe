/**
 * R2-A: the memory types in their own module.
 *
 * types.ts was the filing place for everything; with the migration preview it
 * would have grown past the file-size wall of the architecture gate. The facade
 * stays: types.ts re-exports, so no importer has to move.
 */
export interface MemoryEntry {
  id: string
  text: string
  metadata: Record<string, unknown>
}
/**
 * D5: the Memory surface has to be able to say *which brain* answers and what of
 * it is deleted. `provider`/`deleted` are additive — a stats payload from before
 * wave D carries neither, and `undefined` means "no trash".
 */
export interface MemoryStats {
  total: number
  scope?: string
  provider?: string
  /** R2-A: why this brain answers (env, provider.json, resolution). */
  reason?: string
  vector_leg?: boolean
  lexical_leg?: boolean
  deleted?: number
  /**
   * Wave 10 (additive): whether the active store keeps a deleted entry at all.
   * `deleted: 0` is only honest while the surface can say that this store keeps
   * nothing to restore (walkthrough 2026-10-12, finding 1). Absent means the
   * backend predates the field — the surface then offers restore as before.
   */
  restore_supported?: boolean
  /**
   * Wave 10 (additive): the store's origin vocabulary — every `source` value a
   * row can carry, with the label to print for it. The page's own label map knew
   * only `auto_memory` and `compaction`, so the tool-written rows showed no
   * origin (walkthrough 2026-10-12: 32 rows, 29 chips).
   */
  sources?: Record<string, string>
}

/**
 * The trash answer. `restore_supported` is the promise told honestly: an empty
 * `entries` under a store that deletes finally is the truth about that store,
 * with `detail` as the one line to say why.
 */
export interface MemoryTrash {
  entries: MemoryEntry[]
  total: number
  restore_supported?: boolean
  detail?: string
}

/** Report from POST /api/memory/migrate — the dry run is the decision. */
export interface MigrateReport {
  dry_run: boolean
  provider_source: string
  provider_target: string
  source_total: number
  source_remaining: number
  imported: number
  skipped: number
  target_total: number
  scope: string
  target_path: string
}
