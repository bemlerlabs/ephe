/**
 * What the landing page is allowed to state, and the file that holds each statement.
 *
 * A landing page ages worst where it states facts: a number loses its source, a path is
 * renamed, a command drifts from the README. `landingFacts.test.ts` reads this module and
 * the checkout, so a row whose proof file disappeared fails the suite instead of shipping.
 */
export const REPO_URL = 'https://github.com/bemlerlabs/ephe'
const RAW = 'https://raw.githubusercontent.com/bemlerlabs/ephe'

/** The installer URL names the release this tree carries — the same version the UI prints. */
export const INSTALL_VERSION = __APP_VERSION__

export const REPO_BLOB = `${REPO_URL}/blob/v${INSTALL_VERSION}/`

export const INSTALL_COMMAND = `curl -fsSL ${RAW}/v${INSTALL_VERSION}/install.sh | bash -s -- --tag v${INSTALL_VERSION}`
export const WINDOWS_COMMAND = `irm ${RAW}/v${INSTALL_VERSION}/install.ps1 -OutFile install.ps1`

export const SWITCHING_DOC = `${REPO_BLOB}docs/SWITCHING.md`

/** The two measurements the proof row prints, as the papers report them. */
export const STUDIES = {
  agentsMd: {
    href: 'https://arxiv.org/abs/2601.20404',
    runtimePct: 28.64,
    tokensPct: 16.58,
    pullRequests: 124,
    repositories: 10,
  },
  realm: {
    href: 'https://aclanthology.org/2026.realm-1.5/',
    tasks: 17,
    runs: 288,
    /** Equivalence bound in percentage points, lower and upper. */
    equivalencePp: [10, 15],
  },
} as const

export type ComparisonRowId =
  'engine' | 'account' | 'license' | 'plugins' | 'context' | 'verification'

export interface ComparisonRow {
  id: ComparisonRowId
  questionKey: string
  answerKey: string
  /** Path inside the checkout, relative to its root; the cell links to it on the release this tree ships. */
  proofPath: string
}

export const COMPARISON_ROWS: readonly ComparisonRow[] = [
  {
    id: 'engine',
    questionKey: 'landing.row.engineQuestion',
    answerKey: 'landing.row.engineAnswer',
    proofPath: 'core/engine_config.py',
  },
  {
    id: 'account',
    questionKey: 'landing.row.accountQuestion',
    answerKey: 'landing.row.accountAnswer',
    proofPath: 'README.md',
  },
  {
    id: 'license',
    questionKey: 'landing.row.licenseQuestion',
    answerKey: 'landing.row.licenseAnswer',
    proofPath: 'LICENSE',
  },
  {
    id: 'plugins',
    questionKey: 'landing.row.pluginsQuestion',
    answerKey: 'landing.row.pluginsAnswer',
    proofPath: 'docs/PLUGINS_OVERVIEW.md',
  },
  {
    id: 'context',
    questionKey: 'landing.row.contextQuestion',
    answerKey: 'landing.row.contextAnswer',
    proofPath: 'core/workspace_rules.py',
  },
  {
    id: 'verification',
    questionKey: 'landing.row.verificationQuestion',
    answerKey: 'landing.row.verificationAnswer',
    proofPath: '.github/workflows/ci-gates.yml',
  },
] as const

/** Rows of the import table: the artifact found in an existing setup, and where it lands. */
export const IMPORT_ROWS = [
  {
    id: 'persona',
    artifactKey: 'landing.migrate.persona',
    landsKey: 'landing.migrate.personaLands',
  },
  { id: 'skills', artifactKey: 'landing.migrate.skills', landsKey: 'landing.migrate.skillsLands' },
  { id: 'mcp', artifactKey: 'landing.migrate.mcp', landsKey: 'landing.migrate.mcpLands' },
  {
    id: 'settings',
    artifactKey: 'landing.migrate.settings',
    landsKey: 'landing.migrate.settingsLands',
  },
] as const

export const IMPORT_COMMAND = 'ephe import ~/path-to-your-old-agent-setup'
