import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getCapabilities, type McpSandboxView } from '@/lib/api'

// One question per page life: every card on the MCP list asks the same route.
let facts: Promise<McpSandboxView | null> | null = null

function loadFacts(): Promise<McpSandboxView | null> {
  // A suite that mocks `@/lib/api` for another surface may not carry this route.
  if (typeof getCapabilities !== 'function') return Promise.resolve(null)
  facts ??= getCapabilities()
    .then((view) => view.mcp_sandbox ?? null)
    .catch(() => null)
  return facts
}

/** Test seam: the cache outlives a single render, so suites start from a clean one. */
export function resetMcpSandboxFacts(): void {
  facts = null
}

/**
 * G9: what an MCP server actually runs under — the platform boundary, where its
 * files live and which namespaces are shared. The values come from
 * `core/mcp_sandbox.py` through `/api/capabilities`, so the card cannot claim a
 * boundary the sandbox does not build.
 */
export function McpSandboxStrip({ server }: { server: string }) {
  const { t } = useTranslation()
  const [sandbox, setSandbox] = useState<McpSandboxView | null>(null)

  useEffect(() => {
    let alive = true
    void loadFacts().then((value) => {
      if (alive) setSandbox(value)
    })
    return () => {
      alive = false
    }
  }, [])

  if (!sandbox) return null
  const state = (isolated: boolean) =>
    t(isolated ? 'settings.mcpSandboxIsolated' : 'settings.mcpSandboxShared')
  const line = t('settings.mcpSandbox', {
    platform: sandbox.platform,
    files: sandbox.home_root,
    net: state(sandbox.network_isolated),
    pid: state(sandbox.pid_isolated),
  })

  return (
    <p
      data-testid={`mcp-sandbox-${server}`}
      title={line}
      className="truncate text-ui-2xs tabular-nums text-ink-faint"
    >
      {line}
    </p>
  )
}
