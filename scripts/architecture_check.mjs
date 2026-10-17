#!/usr/bin/env node
/**
 * ◑ Ephe – W3a (2026-09-24): architecture checker (plan step 2).
 * scripts/architecture_check.mjs
 *
 * Node stdlib only, no deps. Modes:
 *   node scripts/architecture_check.mjs check   [--changed] [--module <id>] [--baseline <path>]
 *   node scripts/architecture_check.mjs report  [--changed] [--module <id>] [--baseline <path>]
 *   node scripts/architecture_check.mjs baseline:update [--baseline <path>]
 *
 * Rules per module: maxFileLines, maxContractLines, maxPublicMethods,
 * forbidCycles (Tarjan-SCC), forbidDeepImports.
 * Baseline logic: no .architecture-baseline.json => every finding is a hint,
 * exit 0. Present => finding count per rule above the frozen value = error (exit 1).
 * --baseline <path> moves the read AND the write to that file; the test suite
 * pins its verdicts on private copies that way, so a `pytest -n 8` worker
 * rewriting one never overlaps a worker reading the same path.
 */
import { readFileSync, existsSync, readdirSync, writeFileSync, renameSync, statSync } from 'node:fs';
import { join, dirname, relative, sep } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { argv, exit, pid } from 'node:process';
import { importSpecifiers } from './import_scan.mjs';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const POLICY_PATH = join(ROOT, 'architecture-policy.yaml');
const DEFAULT_BASELINE_PATH = join(ROOT, '.architecture-baseline.json');
// Reassigned by `--baseline <path>` in the arg block near the bottom, before any
// mode runs, so a read and a write in one invocation always name the same file.
let BASELINE_PATH = DEFAULT_BASELINE_PATH;

// mini-YAML
// Parser for the regular subset of architecture-policy.yaml:
// key: scalar | key: [] | key: [a, b] | nested maps | lists of
// scalars and maps started by "- key:".
function parseMiniYaml(text) {
  const lines = text
    .split(/\r?\n/)
    .map((raw) => {
      const noComment = raw.replace(/\s+#.*$/, '');
      return { indent: noComment.match(/^ */)[0].length, body: noComment.trim() };
    })
    .filter((l) => l.body.length > 0 && !l.body.startsWith('#'));

  let i = 0;
  const scalar = (tok) => {
    const t = tok.trim();
    if (t === '[]') return [];
    if (t === 'true') return true;
    if (t === 'false') return false;
    if (/^-?\d+$/.test(t)) return Number(t);
    return t.replace(/^["']|["']$/g, '');
  };
  const inlineList = (t) =>
    t
      .replace(/^\[|\]$/g, '')
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
      .map((x) => x.replace(/^["']|["']$/g, ''));

  function parseBlock(indent) {
    // map or list, decided by the first line
    if (i >= lines.length || lines[i].indent < indent) return null;
    if (lines[i].body.startsWith('- ') || lines[i].body === '-') {
      const out = [];
      while (i < lines.length && lines[i].indent === indent && lines[i].body.startsWith('-')) {
        const first = lines[i];
        const rest = first.body.replace(/^-\s?/, '');
        const kv = rest.match(/^([\w.\-]+):\s*(.*)$/);
        if (!kv) {
          out.push(scalar(rest));
          i += 1;
          continue;
        }
        const obj = {};
        // the first field sits on the line starting with "- "
        const childIndent = first.indent + 2;
        if (kv[2] !== '') {
          obj[kv[1]] = kv[2].startsWith('[') ? inlineList(kv[2]) : scalar(kv[2]);
          i += 1;
        } else {
          i += 1;
          obj[kv[1]] = parseBlock(childIndent);
        }
        // remaining fields of this list item (indent = first.indent + 2)
        while (
          i < lines.length &&
          lines[i].indent === childIndent &&
          !lines[i].body.startsWith('- ')
        ) {
          const m = lines[i].body.match(/^([\w.\-]+):\s*(.*)$/);
          if (!m) break;
          if (m[2] !== '') {
            obj[m[1]] = m[2].startsWith('[') ? inlineList(m[2]) : scalar(m[2]);
            i += 1;
          } else {
            i += 1;
            obj[m[1]] = parseBlock(lines[i] ? lines[i].indent : childIndent + 2);
          }
        }
        out.push(obj);
      }
      return out;
    }
    const obj = {};
    while (i < lines.length && lines[i].indent === indent) {
      const m = lines[i].body.match(/^([\w.\-]+):\s*(.*)$/);
      if (!m) break;
      if (m[2] !== '') {
        obj[m[1]] = m[2].startsWith('[') ? inlineList(m[2]) : scalar(m[2]);
        i += 1;
      } else {
        i += 1;
        const child = lines[i];
        obj[m[1]] = child && child.indent > indent ? parseBlock(child.indent) : null;
      }
    }
    return obj;
  }
  return parseBlock(lines[0] ? lines[0].indent : 0);
}

// helpers
const TS_EXT = ['.ts', '.tsx', '.js', '.jsx', '.mjs'];
const PY_EXT = ['.py'];

function extsFor(moduleId) {
  return moduleId === 'app-frontend' ? TS_EXT : PY_EXT;
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

function countLines(file) {
  const content = readFileSync(file, 'utf-8');
  const parts = content.split('\n');
  return content.endsWith('\n') ? parts.length - 1 : parts.length;
}

function countPublicSymbols(file) {
  const content = readFileSync(file, 'utf-8');
  let n = 0;
  for (const _ of content.matchAll(/export\s+(?:const|function|class|interface|type|default)\b/g)) n += 1;
  for (const m of content.matchAll(/export\s*\{([^}]*)\}/g)) {
    n += m[1]
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s && !s.startsWith('//'))
      .length;
  }
  return n;
}

function resolveSpecifier(fromFile, spec, exts) {
  if (!spec || spec.startsWith('.') === false) {
    if (spec.startsWith('@/')) {
      const base = join(ROOT, 'app', 'src', spec.slice(2));
      return tryModules(base, exts);
    }
    return null; // bare specifier -> outside the repo scope
  }
  const base = join(dirname(fromFile), spec);
  return tryModules(base, exts);
}

function tryModules(base, exts) {
  const cands = [];
  for (const e of exts) cands.push(base + e);
  for (const e of exts) {
    cands.push(join(base, 'index' + e));
  }
  cands.push(join(base, '__init__.py'));
  for (const c of cands) {
    if (existsSync(c) && statSync(c).isFile()) return c;
  }
  return null;
}

function importsOf(file) {
  const content = readFileSync(file, 'utf-8');
  // Code, not prose: a comment that names a module path must not become an edge.
  return importSpecifiers(content, '.' + file.split('.').pop());
}

// Tarjan-SCC over the import graph edges; returns SCCs with >1 node or a self-loop.
function findCycles(nodes, edges) {
  let index = 0;
  const stack = [];
  const onStack = new Set();
  const idx = new Map();
  const low = new Map();
  const sccs = [];
  const selfLoops = new Set();
  const strong = (v) => {
    idx.set(v, index);
    low.set(v, index);
    index += 1;
    stack.push(v);
    onStack.add(v);
    for (const w of edges.get(v) || []) {
      if (w === v) selfLoops.add(v);
      if (!idx.has(w)) {
        strong(w);
        low.set(v, Math.min(low.get(v), low.get(w)));
      } else if (onStack.has(w)) {
        low.set(v, Math.min(low.get(v), idx.get(w)));
      }
    }
    if (low.get(v) === idx.get(v)) {
      const comp = [];
      let w;
      do {
        w = stack.pop();
        onStack.delete(w);
        comp.push(w);
      } while (w !== v);
      if (comp.length > 1) sccs.push(comp);
    }
  };
  for (const v of nodes) if (!idx.has(v)) strong(v);
  return { sccs, selfLoops };
}

// core checks
function rel(p) {
  return relative(ROOT, p).split(sep).join('/');
}

function collectFindings(policy, changedSet, moduleFilter) {
  const findings = [];
  const g = policy.global;
  for (const mod of policy.modules) {
    if (moduleFilter && mod.id !== moduleFilter) continue;
    const exts = extsFor(mod.id);
    const rootDirs = (mod.roots || []).map((r) => join(ROOT, r));
    const inRoots = new Set();
    const files = [];
    for (const rd of rootDirs) {
      for (const f of listFiles(rd)) {
        if (exts.includes('.' + f.split('.').pop())) {
          files.push(f);
          inRoots.add(rel(f));
        }
      }
    }
    const entrySet = new Set((mod.publicEntrypoints || []).map((e) => e));
    const matches = (f) => !changedSet || changedSet.has(f);

    // R1 maxFileLines
    for (const f of files) {
      const r = rel(f);
      if (!matches(r)) continue;
      const n = countLines(f);
      if (n > g.maxFileLines) {
        findings.push({ rule: 'maxFileLines', module: mod.id, file: r, value: n, limit: g.maxFileLines, severity: 'info' });
      }
    }
    // R2 maxContractLines (facade / contract files)
    for (const e of mod.publicEntrypoints || []) {
      if (!matches(e)) continue;
      const full = join(ROOT, e);
      if (!existsSync(full)) continue;
      const n = countLines(full);
      if (n > g.maxContractLines) {
        findings.push({ rule: 'maxContractLines', module: mod.id, file: e, value: n, limit: g.maxContractLines, severity: 'info' });
      }
    }
    // R3 maxPublicMethods per public symbol container
    for (const e of mod.publicEntrypoints || []) {
      if (!matches(e)) continue;
      const full = join(ROOT, e);
      if (!existsSync(full)) continue;
      const n = countPublicSymbols(full);
      if (n > g.maxPublicMethods) {
        findings.push({ rule: 'maxPublicMethods', module: mod.id, file: e, value: n, limit: g.maxPublicMethods, severity: 'info' });
      }
    }
    // R4 import cycles (Tarjan) across the module roots
    if (g.forbidCycles) {
      const edges = new Map();
      for (const f of files) {
        const out = [];
        for (const spec of importsOf(f)) {
          const target = resolveSpecifier(f, spec, exts);
          if (target && inRoots.has(rel(target))) out.push(rel(target));
        }
        edges.set(rel(f), out);
      }
      const { sccs, selfLoops } = findCycles([...inRoots], edges);
      for (const comp of sccs) {
        for (const node of comp) {
          if (!matches(node)) continue;
          findings.push({
            rule: 'forbidCycles',
            module: mod.id,
            file: node,
            value: comp.length,
            limit: 1,
            severity: 'info',
          });
        }
      }
      for (const node of selfLoops) {
        if (!matches(node)) continue;
        findings.push({ rule: 'forbidCycles', module: mod.id, file: node, value: 1, limit: 0, severity: 'info' });
      }
    }
    // R5 deep import: a non-index file of a facade root imported from outside it
    if (g.forbidDeepImports) {
      const outsideDirs = mod.id === 'app-frontend' ? [join(ROOT, 'app', 'src')] : rootDirs[0] ? [join(ROOT, mod.roots[0].split('/')[0] || '.')] : [];
      const outsideFiles = new Set();
      for (const od of outsideDirs) for (const f of listFiles(od)) outsideFiles.add(f);
      for (const f of outsideFiles) {
        const r = rel(f);
        if (inRoots.has(r)) continue;
        if (!exts.includes('.' + f.split('.').pop())) continue;
        if (!matches(r)) continue;
        for (const spec of importsOf(f)) {
          const target = resolveSpecifier(f, spec, exts);
          if (!target) continue;
          const tr = rel(target);
          if (!inRoots.has(tr)) continue;
          const base = target.split('/').pop().replace(/\.[a-z]+$/, '');
          if (base !== 'index' && base !== '__init__') {
            findings.push({ rule: 'forbidDeepImports', module: mod.id, file: r, value: 1, limit: 0, severity: 'info' });
          }
        }
      }
    }
  }
  return findings;
}

function applyBaseline(findings, baseline) {
  if (!baseline) return findings; // no baseline => everything is a hint
  const perRule = baseline.perRule || {};
  const current = {};
  for (const f of findings) current[f.rule] = (current[f.rule] || 0) + 1;
  return findings.map((f) => ({
    ...f,
    severity: (perRule[f.rule] ?? 0) < current[f.rule] ? 'error' : 'info',
  }));
}

function buildReport(policy, changedSet, moduleFilter) {
  const raw = collectFindings(policy, changedSet, moduleFilter);
  const baseline = existsSync(BASELINE_PATH)
    ? JSON.parse(readFileSync(BASELINE_PATH, 'utf-8'))
    : null;
  const findings = applyBaseline(raw, baseline);
  const counts = { total: findings.length, info: 0, error: 0 };
  for (const f of findings) counts[f.severity] = (counts[f.severity] || 0) + 1;
  return {
    policyVersion: policy.version,
    managedModules: policy.modules.filter((m) => m.managed === true).length,
    findings,
    counts,
    baselinePresent: Boolean(baseline),
  };
}

function changedFiles() {
  try {
    const tracked = execFileSync('git', ['diff', '--name-only', 'HEAD'], { cwd: ROOT, encoding: 'utf-8' });
    const untracked = execFileSync('git', ['ls-files', '--others', '--exclude-standard'], { cwd: ROOT, encoding: 'utf-8' });
    return new Set([...tracked.split('\n'), ...untracked.split('\n')].map((s) => s.trim()).filter(Boolean));
  } catch {
    return new Set();
  }
}

// main
const args = argv.slice(2);
const mode = args[0] || 'check';
if (args.includes('--baseline')) {
  const value = args[args.indexOf('--baseline') + 1];
  if (!value || value.startsWith('--')) {
    console.error('--baseline needs a path, e.g. --baseline /tmp/arch-copy.json');
    exit(1);
  }
  BASELINE_PATH = value;
}
const moduleFilter = args.includes('--module') ? args[args.indexOf('--module') + 1] : null;
const useChanged = args.includes('--changed');

if (!existsSync(POLICY_PATH)) {
  console.error('architecture-policy.yaml not found at the repo root');
  exit(1);
}
const policy = parseMiniYaml(readFileSync(POLICY_PATH, 'utf-8'));
const changedSet = useChanged ? changedFiles() : null;

if (mode === 'report') {
  console.log(JSON.stringify(buildReport(policy, changedSet, moduleFilter), null, 2));
  exit(0);
}

if (mode === 'baseline:update') {
  const report = buildReport(policy, null, null);
  const perRule = {};
  for (const f of report.findings) perRule[f.rule] = (perRule[f.rule] || 0) + 1;
  const snap = {
    policyVersion: policy.version,
    frozenAt: new Date().toISOString(),
    perRule,
    total: report.findings.length,
  };
  // Write-then-rename: a plain write truncates first, and a reader in another
  // process (a pytest worker on the same file) can land inside that window.
  const tmp = `${BASELINE_PATH}.${pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(snap, null, 2) + '\n', 'utf-8');
  renameSync(tmp, BASELINE_PATH);
  console.log(`baseline written: ${rel(BASELINE_PATH)} (${report.findings.length} findings)`);
  exit(0);
}

// mode 'check'
const report = buildReport(policy, changedSet, moduleFilter);
// Severity is decided per rule against the frozen count, and --changed counts only the
// changed files, so this run can print "info" where the whole-tree run prints "error".
// The whole-tree run is the contract; this notice keeps the two verdicts distinguishable.
if (useChanged) {
  console.log('arch-check: --changed scored the changed files only, so a rule can read "info" here where the whole-tree run calls it an error; the contract is the whole-tree run in .github/workflows/ci-gates.yml.');
}
for (const f of report.findings) {
  console.log(`[${f.severity}] ${f.rule} ${f.module} ${f.file} (value=${f.value} limit=${f.limit})`);
}
console.log(`arch-check: ${report.counts.total} findings (${report.counts.error} errors, ${report.counts.info} hints), baseline=${report.baselinePresent}`);
exit(report.counts.error > 0 ? 1 : 0);
