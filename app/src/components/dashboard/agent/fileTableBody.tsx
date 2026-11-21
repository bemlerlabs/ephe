'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { filePreviewByPath, type ArtifactContentPreview } from '@/lib/api'
import { LoadingRow } from '@/components/ui'
import { PayloadView } from '@/components/dashboard/artifacts/preview'
import type { OpenFile } from '@/lib/workspaceFiles'
import type { FileView } from '@/lib/fileOpen'
import { FilePreviewBody } from './filePreview'

/**
 * Ephe — the workspace column's table view for a file that is a table *and* text (a CSV).
 *
 * The workbench card has drawn a `.csv` as rows since `core/artifact_preview.py` put the
 * suffix in its `TABLE_KINDS`; the column, reading the same bytes through `PLAIN_EXT`, only
 * ever showed a code block. The file is both things, so the column keeps both views — the
 * server's table and the source text — exactly as it keeps page and source for Markdown.
 *
 * The rendered view asks `/api/file/preview` by path and shares `PayloadView`, the one table
 * renderer, rather than drawing a second one. Where the server declines — `mode: "none"` for
 * a file it cannot open, or a request that never lands — the view does not go to an empty
 * frame: it falls back to the bytes, which stay reachable and copyable. The decline shows as
 * a readable file, never as a blank pane.
 */

function CsvSource({ file, onReload }: { file: OpenFile; onReload: () => void }) {
  return (
    <FilePreviewBody
      preview={{ kind: 'code', path: file.path, filename: file.name, language: 'text' }}
      onReload={onReload}
    />
  )
}

export function FileTableBody({
  file,
  view,
  nonce,
  onReload,
}: {
  file: OpenFile
  view: FileView
  nonce: number
  onReload: () => void
}) {
  const { t } = useTranslation()
  const [data, setData] = useState<ArtifactContentPreview | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (view !== 'rendered') return
    let cancelled = false
    setData(null)
    setFailed(false)
    filePreviewByPath(file.path)
      .then((answer) => {
        if (!cancelled) setData(answer)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [file.path, nonce, view])

  if (view === 'source') return <CsvSource file={file} onReload={onReload} />
  if (failed || (data && data.mode === 'none')) {
    return <CsvSource file={file} onReload={onReload} />
  }
  if (!data) {
    return <LoadingRow label={t('artifacts.preview.loading')} className="h-full justify-center" />
  }
  return <PayloadView data={data} name={file.name} />
}
