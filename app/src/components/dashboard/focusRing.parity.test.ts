/**
 * Wave U1 — focus-ring parity for popover/context menu items (P1-2 completion).
 *
 * Every keyboard-focusable element inside a popover or context menu must show
 * a visible focus indicator (WCAG 2.4.7), same ring pattern as the settings
 * fields (P0-3): focus-visible:outline-2 outline-solid outline-ring.
 *
 * Static convention scan (same style as the wave10 k-parity tests): for each
 * anchor line we extract the enclosing <button …> opening tag and require the
 * ring classes inside it. A per-file ring-count guard catches drift if a
 * future refactor moves className out of the opening tag.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// One ring in the program: --color-ring (emerald) is the focus tone, not the
// brand-red accent firefly. Red on the outline of a neutral field reads
// as a validation error.
const RING = 'focus-visible:outline-ring'

const FILES: Record<string, string[]> = {
  'ChatInput.tsx': ['role="menuitem"'],
  'Sidebar.tsx': ['role="menuitem"'],
  'WorkspaceBar.tsx': ['role="menuitem"'],
  'agent/previewTab.tsx': ['role="menuitem"'],
  'AgentStatusButton.tsx': [
    'data-testid="agent-status-collapse"',
    'data-testid="agent-status-subagent-',
    'data-testid="agent-status-tasks-link"',
  ],
}

function openingTag(lines: string[], anchorIdx: number): string {
  let start = anchorIdx
  while (start > 0 && !(lines[start]?.includes('<button') ?? false)) start -= 1
  let end = anchorIdx
  while (end < lines.length - 1 && !(lines[end]?.trim().endsWith('>') ?? false)) end += 1
  return lines.slice(start, end + 1).join('\n')
}

function scan(file: string, anchors: string[]): string[] {
  const text = readFileSync(fileURLToPath(new URL(file, import.meta.url)), 'utf-8')
  const lines = text.split('\n')
  const failures: string[] = []
  let anchorCount = 0
  lines.forEach((line, i) => {
    if (!anchors.some((a) => line.includes(a))) return
    // A CSS selector is not a JSX attribute: `querySelector('[role="menuitem"]')` in the
    // keyboard code would otherwise be read as a menu item whose ring went missing.
    if (line.includes('[role=')) return
    anchorCount += 1
    if (!openingTag(lines, i).includes(RING)) {
      failures.push(`${file}:${i + 1} (${line.trim().slice(0, 60)})`)
    }
  })
  const ringCount = lines.filter((l) => l.includes(RING)).length
  if (ringCount < anchorCount) {
    failures.push(`${file}: ring count ${ringCount} < anchor count ${anchorCount}`)
  }
  return failures
}

describe('focus-ring parity — popover/menu items (Welle U1)', () => {
  it('every menu item and status-popover button carries the focus ring', () => {
    const failures = Object.entries(FILES).flatMap(([file, anchors]) => scan(file, anchors))
    expect(failures).toEqual([])
  })

  it('every menu host dismisses on Escape (U1b keyboard parity)', () => {
    const missing = Object.keys(FILES).filter((file) => {
      const text = readFileSync(fileURLToPath(new URL(file, import.meta.url)), 'utf-8')
      return !text.includes("'Escape'")
    })
    expect(missing).toEqual([])
  })
})
