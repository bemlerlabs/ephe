/**
 * P6 B2 (per-section collapse norm): the scroll policy per status section. The
 * table is the ONE source for the maximum height of a section body — every
 * section scrolls on its own while the popup itself keeps its compact height.
 */

/** Catalog of the status popup's sections (B2: 6 core sections, B3: environment,
 *  wave 3: usage — Kosten & Verbrauch, language-gate: ignore — the label de.json:1408 renders). */
export type StatusSectionKind =
  | 'goal'
  | 'sessionPlans'
  | 'plan'
  | 'terminal'
  | 'workflow'
  | 'agent'
  | 'environment'
  | 'queries'
  | 'usage'

/** The max-h class per section — deliberately class- (not pixel-) based, so the
 *  test can verify the contract directly on the DOM. */
export const STATUS_SECTION_SCROLL_POLICY = {
  goal: 'max-h-48',
  sessionPlans: 'max-h-48',
  plan: 'max-h-80',
  terminal: 'max-h-48',
  workflow: 'max-h-48',
  agent: 'max-h-48',
  environment: 'max-h-48',
  queries: 'max-h-48',
  usage: 'max-h-48',
} as const satisfies Record<StatusSectionKind, string>
