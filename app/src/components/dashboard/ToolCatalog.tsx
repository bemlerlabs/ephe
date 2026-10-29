/**
 * R3: the tools Ephe registers, each with the gate's own verdict.
 *
 * `safe` comes from the server, which reads `SAFE_TOOLS` — the list that decides a
 * call runs without a prompt. The row therefore cannot claim a freedom the guard
 * would refuse. A server without the block renders nothing.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Code2,
  FileText,
  FolderOpen,
  Globe,
  Search,
  Terminal,
  Users,
  Wrench,
} from 'lucide-react'
import { Card } from '@/components/ui'
import { getCapabilities, type ToolCatalogRow } from '@/lib/api'

const ICONS: Record<string, typeof Wrench> = {
  read_file: FileText,
  edit_file: FileText,
  write_file: FileText,
  list_directory: FolderOpen,
  file_search: Search,
  fetch_url: Globe,
  browser_go: Globe,
  browser_screenshot: Globe,
  execute_code: Code2,
  run_shell: Terminal,
  spawn_agent: Users,
  agent_message: Users,
}

function iconFor(name: string) {
  return ICONS[name] ?? Wrench
}

export function ToolCatalog() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<ToolCatalogRow[] | null>(null)

  useEffect(() => {
    let alive = true
    getCapabilities()
      .then((view) => {
        if (alive) setRows(view.tools?.tools ?? null)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  if (!rows || rows.length === 0) return null
  const safe = rows.filter((row) => row.safe).length

  return (
    <Card data-testid="tools-catalog">
      <h3 className="flex items-center gap-2 font-display text-ui-lg font-semibold text-foreground/95">
        <Wrench className="h-4 w-4" strokeWidth={1.5} aria-hidden="true" />
        {t('tools.catalogTitle')}
      </h3>
      <p className="mt-1 text-ui-sm text-ink-faint">
        {t('tools.catalogHint', { safe, total: rows.length })}
      </p>
      <ul className="mt-3 divide-y divide-hairline">
        {rows.map((row) => {
          const Icon = iconFor(row.name)
          return (
            <li
              key={row.name}
              data-testid={`tool-row-${row.name}`}
              data-safe={row.safe ? 'true' : 'false'}
              className="flex items-center gap-2 py-1.5"
            >
              <Icon
                className="h-4 w-4 shrink-0 text-ink-faint"
                strokeWidth={1.5}
                aria-hidden="true"
              />
              <span className="shrink-0 font-mono text-ui-xs text-foreground/90">{row.name}</span>
              <span className="min-w-0 flex-1 truncate text-ui-xs text-ink-faint">
                {row.description}
              </span>
              <span
                className={`shrink-0 text-ui-2xs ${
                  row.safe ? 'text-status-success/90' : 'text-status-warning/90'
                }`}
              >
                {row.safe ? t('tools.catalogSafe') : t('tools.catalogAsks')}
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
