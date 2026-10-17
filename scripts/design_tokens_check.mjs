#!/usr/bin/env node
/**
 * design_tokens_check.mjs - frozen-baseline gate against raw design values.
 *
 * Node stdlib only, no deps. Modes:
 *   node scripts/design_tokens_check.mjs check   [--baseline <path>]
 *   node scripts/design_tokens_check.mjs report  [--baseline <path>]
 *   node scripts/design_tokens_check.mjs baseline:update [--baseline <path>]
 *
 * Axes, counted over app/src *.ts and *.tsx (a *.test.* or *.spec.* name skips):
 *   radiusArbitrary  rounded-[...]        arbitrary corner radius
 *   shadowArbitrary  shadow-[...]         arbitrary shadow
 *   colorLiteral     raw colour literals  bracket forms plus bare hex/rgb/hsl
 *
 * Baseline logic: no .design-tokens-baseline.json => every finding is a hint, exit 0.
 * Present => a per-axis count above the frozen value turns that axis's findings into
 * errors (exit 1). --baseline <path> moves the read AND the write to that file, so a
 * test suite can pin a verdict on a private copy and never touch the tracked freeze.
 */
import { readFileSync, existsSync, readdirSync, writeFileSync, renameSync } from 'node:fs';
import { join, dirname, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { argv, exit, pid } from 'node:process';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const SCAN_ROOT = join(ROOT, 'app', 'src');
const DEFAULT_BASELINE_PATH = join(ROOT, '.design-tokens-baseline.json');
const VERSION = 1;
// Reassigned by `--baseline <path>` in the arg block below, before any mode runs, so a
// read and a write in one invocation always name the same file.
let BASELINE_PATH = DEFAULT_BASELINE_PATH;

const EXTS = ['.ts', '.tsx'];
const SKIP_NAME = /\.(test|spec)\./;

// One ordered list; the report, the snapshot and the print all walk it in this order.
const AXES = [
  { axis: 'radiusArbitrary', pattern: /rounded-\[[^\]]+\]/g },
  { axis: 'shadowArbitrary', pattern: /shadow-\[[^\]]+\]/g },
  {
    axis: 'colorLiteral',
    pattern: /\[#[0-9a-fA-F]{3,8}\]|\[rgb[^\]]*\]|\[hsl[^\]]*\]|#[0-9a-fA-F]{6}|rgb\([^)]*\)|hsl\([^)]*\)/g,
  },
];

function rel(p) {
  return relative(ROOT, p).split(sep).join('/');
}

function listFiles(dir) {
  const out = [];
  if (!existsSync(dir)) return out;
  const walk = (d) => {
    for (const ent of readdirSync(d, { withFileTypes: true })) {
      const name = ent.name;
      if (name === 'node_modules' || name === '__pycache__' || name === '.venv') continue;
      const full = join(d, name);
      if (ent.isDirectory()) walk(full);
      else if (ent.isFile()) out.push(full);
    }
  };
  walk(dir);
  return out;
}

function scannedFiles() {
  const out = [];
  for (const full of listFiles(SCAN_ROOT)) {
    const dot = full.lastIndexOf('.');
    const ext = dot < 0 ? '' : full.slice(dot);
    if (!EXTS.includes(ext)) continue;
    const base = full.slice(full.lastIndexOf(sep) + 1);
    if (SKIP_NAME.test(base)) continue;
    out.push(rel(full));
  }
  return out.sort();
}

// One finding per axis per file: value is that file's occurrence count, and limit is
// filled from the frozen baseline in applyBaseline (0 while no baseline is present).
function collectFindings() {
  const files = scannedFiles();
  const texts = new Map(files.map((f) => [f, readFileSync(join(ROOT, f), 'utf-8')]));
  const findings = [];
  for (const { axis, pattern } of AXES) {
    for (const file of files) {
      const hits = texts.get(file).match(pattern);
      if (hits && hits.length > 0) {
        findings.push({ axis, file, value: hits.length, limit: 0, severity: 'info' });
      }
    }
  }
  return findings;
}

// Aggregate per-axis occurrence totals, not a finding count: the baseline freezes how
// many raw values exist, which is what later growth is measured against. Axes with no
// finding stay at 0, so the snapshot names all three.
function perAxisTotals(findings) {
  const totals = {};
  for (const { axis } of AXES) totals[axis] = 0;
  for (const f of findings) totals[f.axis] = (totals[f.axis] || 0) + f.value;
  return totals;
}

function applyBaseline(findings, baseline) {
  if (!baseline) return findings; // no baseline => everything is a hint
  const perAxis = baseline.perAxis || {};
  const current = perAxisTotals(findings);
  return findings.map((f) => ({
    ...f,
    limit: perAxis[f.axis] ?? 0,
    severity: (perAxis[f.axis] ?? 0) < current[f.axis] ? 'error' : 'info',
  }));
}

function buildReport() {
  const raw = collectFindings();
  const baseline = existsSync(BASELINE_PATH)
    ? JSON.parse(readFileSync(BASELINE_PATH, 'utf-8'))
    : null;
  const findings = applyBaseline(raw, baseline);
  const counts = { total: findings.length, info: 0, error: 0 };
  for (const f of findings) counts[f.severity] = (counts[f.severity] || 0) + 1;
  return {
    version: VERSION,
    findings,
    counts,
    perAxis: perAxisTotals(raw),
    baselinePresent: Boolean(baseline),
  };
}

// main
const args = argv.slice(2);
const mode = args[0] || 'check';
if (args.includes('--baseline')) {
  const value = args[args.indexOf('--baseline') + 1];
  if (!value || value.startsWith('--')) {
    console.error('--baseline needs a path, e.g. --baseline /tmp/tokens-copy.json');
    exit(1);
  }
  BASELINE_PATH = value;
}

if (mode === 'report') {
  console.log(JSON.stringify(buildReport(), null, 2));
  exit(0);
}

if (mode === 'baseline:update') {
  const report = buildReport();
  const perAxis = report.perAxis;
  const snap = {
    version: VERSION,
    frozenAt: new Date().toISOString(),
    perAxis,
    total: Object.values(perAxis).reduce((a, b) => a + b, 0),
  };
  // Write-then-rename: a plain write truncates first, and a reader in another process
  // (a pytest worker on the same path) can land inside that window.
  const tmp = `${BASELINE_PATH}.${pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(snap, null, 2) + '\n', 'utf-8');
  renameSync(tmp, BASELINE_PATH);
  console.log(`baseline written: ${rel(BASELINE_PATH)} (${report.counts.total} findings)`);
  exit(0);
}

// mode 'check'
const report = buildReport();
for (const f of report.findings) {
  console.log(`[${f.severity}] ${f.axis} ${f.file} (value=${f.value} limit=${f.limit})`);
}
console.log(`token-check: ${report.counts.total} findings (${report.counts.error} errors, ${report.counts.info} hints), baseline=${report.baselinePresent}`);
exit(report.counts.error > 0 ? 1 : 0);
