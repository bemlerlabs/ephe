/**
 * Ephe — reference-B parity Z01–Z06 (round E): a pure classification model
 * for the tool-call cards in the chat stream.
 *
 * A card should — like the reference harness — reveal in the summary line
 * WHAT is happening right now (icon + verb + human target), and show the
 * details only on expansion. This file makes exclusively data-driven
 * decisions for that (no React, no DOM access), so that it is testable in
 * isolation: family, icon, verb key, target, exit code, diff stats and
 * preview suitability.
 */
import { resolveFilePreview, fileLanguage } from './previewMode'

export type ToolFamily =
  | 'shell'
  | 'edit'
  | 'write'
  | 'read'
  | 'search'
  | 'web'
  | 'task'
  | 'artifact'
  | 'subagent'
  | 'generic'

export type ToolIconKind =
  | 'terminal'
  | 'filePen'
  | 'filePlus'
  | 'fileText'
  | 'search'
  | 'globe'
  | 'tasks'
  | 'package'
  | 'subagent'
  | 'wrench'

/** Which execution carried an `execute_code` turn (wave E1). */
export type CodeRuntime = 'cpython-cell' | 'kernel'

/** Structure-free shadow of ToolCall (types/index.ts) — keeps the model testable. */
export interface ToolCallShape {
  id: string
  name: string
  args?: Record<string, unknown>
  result?: string
  status: string
}

export interface ToolCardModel {
  family: ToolFamily
  icon: ToolIconKind
  /** i18n key of the verb ("Edited", "Ran" …) — de/en parity is mandatory. */
  verbKey: string
  /** Human-readable primary target in the summary line (file name, command, question …). */
  target: string
  /** Terminal rendering only for shell. */
  command: string | null
  /** File path for diff/preview actions, when present. */
  filePath: string | null
  /** Parsed from the run_shell suffix `[exit N] …`; null without an exit marker. */
  exit: { code: number; body: string; err: string } | null
  /** +N/−N line statistics from the unified diff; null for a non-diff. */
  stats: { added: number; removed: number } | null
  /** The file would render meaningfully in the preview tab (Markdown/code/text). */
  previewable: boolean
  /** Highlight language for write_file contents. */
  language: string | null
  /** R36-S: sub-agent id (subagent_started events) for click→transcript tab; null for non-subagents. */
  agentId: string | null
  /** E1: runtime of an execute_code turn taken from the result line; null for non-code. */
  runtime: CodeRuntime | null
}

const ARTIFACT_TOOLS = new Set([
  'create_pdf',
  'create_pitch_deck',
  'create_pptx_deck',
  'create_svg',
  'create_xlsx',
  'create_docx',
  'create_qrcode',
  'create_diagram',
  'build_document',
  'scaffold_project',
  'generate_chart',
  'generate_image',
  'create_source_notebook',
  'export_source_brief',
])

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function basename(p: string): string {
  const parts = (p || '').split('/').filter(Boolean)
  return parts.length > 0 ? (parts[parts.length - 1] as string) : ''
}

/** True when the string looks like a unified diff (header/hunk markers). */
export function isDiffLike(s: string): boolean {
  return s.includes('@@') || s.startsWith('+++') || s.startsWith('---')
}

/** run_shell delivers failures as `out\n[exit N] err` — the error body
 *  after the marker is stderr and has to stay visible (red), not get lost. */
export function parseExitCode(result: string): { code: number; body: string; err: string } | null {
  const m = /\n?\[exit (-?\d+)\]/.exec(result ?? '')
  if (m === null) return null
  const code = Number(m[1])
  if (!Number.isFinite(code)) return null
  return {
    code,
    body: result.slice(0, m.index).trimEnd(),
    err: result.slice(m.index + m[0].length).trim(),
  }
}

/** execute_code confirms in its header line WHICH execution carried the turn
 *  (`[execute_code] runtime=cpython-cell/… status=…`). The panel shows
 *  exactly this runtime proof, so the kernel never stays unnamed. */
export function codeRuntimeFromResult(result: string | undefined): CodeRuntime | null {
  const m = /\[execute_code\] runtime=([a-z-]+)/.exec(result ?? '')
  if (m === null) return null
  return m[1] === 'kernel' || m[1] === 'cpython-cell' ? (m[1] as CodeRuntime) : null
}

/** Counts additions/deletions of a unified diff; do not count the header lines (---/+++). */
export function diffStats(diff: string): { added: number; removed: number } | null {
  if (!diff || !isDiffLike(diff)) return null
  let added = 0
  let removed = 0
  for (const line of diff.split('\n')) {
    if (line.startsWith('+') && !line.startsWith('+++')) added += 1
    else if (line.startsWith('-') && !line.startsWith('---')) removed += 1
  }
  return { added, removed }
}

/** Would this file be real rendering rather than raw markup in the preview tab? */
// Owner wave: the preview iframe renders PDF/HTML/images/audio/video
// natively (browser PDF viewer) — they are preview-capable even though
// resolveFilePreview (the text renderer) does not know them.
export const MEDIA_PREVIEW_EXT = new Set([
  'pdf',
  'html',
  'htm',
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'svg',
  'mp3',
  'wav',
  'mp4',
  'webm',
])

export function filePreviewable(path: string): boolean {
  if (!path) return false
  const ext = (path.split('.').pop() ?? '').toLowerCase()
  if (MEDIA_PREVIEW_EXT.has(ext)) return true
  try {
    return resolveFilePreview(`/api/file?path=${encodeURIComponent(path)}`) !== null
  } catch {
    return false
  }
}

function primaryFileArg(args: Record<string, unknown>): string {
  return (
    str(args.path) ||
    str(args.file_path) ||
    str(args.filename) ||
    str(args.output_path) ||
    str(args.output)
  )
}

/** Deterministic classification per tool name. The unknown stays honestly generic. */
export function classifyToolCall(tool: ToolCallShape): ToolCardModel {
  const args = tool.args ?? {}
  const name = tool.name
  const result = str(tool.result)
  const base: ToolCardModel = {
    family: 'generic',
    icon: 'wrench',
    verbKey: 'chat.toolVerbGeneric',
    target: '',
    command: null,
    filePath: null,
    exit: null,
    stats: null,
    previewable: false,
    language: null,
    agentId: null,
    runtime: codeRuntimeFromResult(result),
  }

  switch (name) {
    case 'run_shell': {
      const command = str(args.command)
      return {
        ...base,
        family: 'shell',
        icon: 'terminal',
        verbKey: 'chat.toolVerbRun',
        command,
        target: command || name,
        exit: parseExitCode(result),
      }
    }
    case 'edit_file': {
      const filePath = primaryFileArg(args)
      return {
        ...base,
        family: 'edit',
        icon: 'filePen',
        verbKey: 'chat.toolVerbEdit',
        filePath,
        target: basename(filePath) || name,
        stats: diffStats(result),
        previewable: filePreviewable(filePath),
      }
    }
    case 'write_file': {
      const filePath = primaryFileArg(args)
      return {
        ...base,
        family: 'write',
        icon: 'filePlus',
        verbKey: 'chat.toolVerbWrite',
        filePath,
        target: basename(filePath) || name,
        stats: diffStats(result),
        previewable: filePreviewable(filePath),
        language: filePath ? fileLanguage(filePath) : null,
      }
    }
    case 'read_file':
    case 'list_directory':
    case 'load_workspace': {
      const filePath = primaryFileArg(args) || str(args.dir) || str(args.directory)
      return {
        ...base,
        family: 'read',
        icon: 'fileText',
        verbKey: 'chat.toolVerbRead',
        target: basename(filePath) || filePath || name,
        filePath: filePath || null,
      }
    }
    case 'file_search':
    case 'discover_projects':
    case 'analyze_project': {
      const q = str(args.query) || str(args.pattern) || str(args.path)
      return {
        ...base,
        family: 'search',
        icon: 'search',
        verbKey: 'chat.toolVerbSearch',
        target: q || name,
      }
    }
    case 'web_search':
    case 'browser_go':
    case 'browser_click':
    case 'browser_type':
    case 'browser_press':
    case 'browser_screenshot': {
      const q = str(args.url) || str(args.query) || str(args.text)
      return {
        ...base,
        family: 'web',
        icon: 'globe',
        verbKey: 'chat.toolVerbBrowse',
        target: q || name,
      }
    }
    case 'manage_tasks': {
      const title = str(args.title)
      return {
        ...base,
        family: 'task',
        icon: 'tasks',
        verbKey: 'chat.toolVerbTask',
        target: title || str(args.action) || name,
      }
    }
    case 'spawn_swarm':
    case 'spawn_agent':
    case 'agent_message': {
      // Reference pattern: `SubAgent general-purpose · P2-Layout + P4-Doku` —
      // role/type + a short description of the job on one line.
      const role = str(args.role) || str(args.task_type) || str(args.subagent_type)
      const firstSubtask = Array.isArray(args.subtasks) ? str((args.subtasks as unknown[])[0]) : ''
      const brief = firstSubtask || str(args.prompt) || str(args.message) || str(args.description)
      const target = [role, brief].filter(Boolean).join(' · ')
      return {
        ...base,
        family: 'subagent',
        icon: 'subagent',
        verbKey: 'chat.toolVerbSubagent',
        target,
        agentId: null,
      }
    }
    default: {
      if (ARTIFACT_TOOLS.has(name)) {
        const filePath = primaryFileArg(args)
        return {
          ...base,
          family: 'artifact',
          icon: 'package',
          verbKey: 'chat.toolVerbArtifact',
          filePath: filePath || null,
          target: basename(filePath) || name,
          previewable: filePreviewable(filePath),
        }
      }
      return { ...base, target: '' }
    }
  }
}

/**
 * K3 Z14 (source bar): URL extraction from a web_search/fetch result.
 * Numbered citations (`1. Title — https://…`) and bare URLs are
 * found; order = first occurrence, capped at 6 (one line in the layout).
 */
export function extractSourceUrls(result: string | undefined): string[] {
  if (!result) return []
  const seen = new Set<string>()
  const re = /https?:\/\/[^\s)\]>]+/g
  let m: RegExpExecArray | null
  while ((m = re.exec(result)) !== null) {
    // Trailing sentence punctuation is trimmed by index. `/[.,;]+$/` is
    // quadratic: on a long run followed by a non-match the engine re-scans the
    // run at every start position.
    let end = m[0].length
    while (end > 0 && '.,;'.includes(m[0].charAt(end - 1))) end -= 1
    const url = m[0].slice(0, end)
    if (url) seen.add(url)
    if (seen.size >= 6) break
  }
  return [...seen]
}
