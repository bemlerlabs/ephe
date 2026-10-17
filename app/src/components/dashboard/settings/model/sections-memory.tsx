'use client'

/**
 * I6-7: the memory section — before, a text field and nothing else.
 *
 * The search was the only control, while the five thresholds that really decide
 * the inventory (when an answer counts as a memory, from where a duplicate
 * starts, how much of it is lifted into the prompt) stood as literals in
 * core/auto_memory.py and core/memory.py. They live in the register now and are
 * read there; this section shows them as rows.
 *
 * The size control (memory_max_entries) stays in the generation block of
 * engine.json — a second field here would be a second number for one ceiling.
 */
import { Ban, Database, Download, FolderTree, Layers, ListChecks, Upload } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { exportMemoryUrl, importMemory } from '@/lib/api'
import { toastBus } from '@/lib/toast'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function MemorySection({ model }: { model: SettingsModel }) {
  const {
    clearMemoryAll,
    confirmClearMemory,
    memoryProvider,
    memoryScope,
    memoryTotal,
    reloadMemory,
    setConfirmClearMemory,
    t,
  } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.memoryTitle')} subtitle={t('settings.memorySubtitle')} />

      <DeepFields model={model} prefixes={['memory.']} />

      <SettingsGroup icon={Database} title={t('settings.memoryGroupStore')}>
        <SettingsRow
          icon={Database}
          title={t('settings.memoryVectors')}
          description={t('settings.memoryVectorsHint')}
          testid="memory-count"
        >
          <span className="font-mono text-ui-xs text-brand/90">
            {memoryTotal === null ? '—' : memoryTotal}
          </span>
        </SettingsRow>
        <SettingsRow
          icon={Layers}
          title={t('settings.memoryProvider')}
          description={t('settings.memoryProviderHint')}
          testid="memory-provider"
        >
          <span className="font-mono text-ui-xs text-foreground/80">{memoryProvider || '—'}</span>
        </SettingsRow>
        {/* R40: without the collection name, "empty" and "wrong folder" are
            indistinguishable — memory is bound to the workspace. */}
        <SettingsRow
          icon={FolderTree}
          title={t('settings.memoryScope')}
          description={t('settings.memoryScopeHint')}
          testid="memory-scope"
        >
          <span
            data-testid="settings-memory-scope"
            className="max-w-[46%] break-all text-right font-mono text-ui-2xs text-ink-faint"
          >
            {memoryScope || '—'}
          </span>
        </SettingsRow>
        <SettingsRow
          icon={Download}
          title={t('settings.memoryExport')}
          description={t('settings.memoryExportHint')}
          testid="memory-export"
        >
          <a
            href={exportMemoryUrl()}
            download
            className="rounded-lg bg-brand/20 px-3 py-1.5 text-ui-xs font-medium text-brand-deep transition-colors hover:bg-brand/20 max-lg:min-h-11"
          >
            {t('settings.memoryExport')}
          </a>
        </SettingsRow>
        <SettingsRow
          icon={Upload}
          title={t('settings.memoryImport')}
          description={t('settings.memoryImportHint')}
          testid="memory-import"
        >
          <label className="cursor-pointer rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors glass-control hover:text-foreground max-lg:min-h-11">
            {t('settings.memoryImport')}
            <input
              type="file"
              accept=".json"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0]
                if (!f) return
                try {
                  const data = JSON.parse(await f.text()) as {
                    entries?: { text: string; metadata?: Record<string, unknown> }[]
                  }
                  const res = await importMemory(data.entries ?? [])
                  toastBus.success(t('settings.memoryImported', { count: res.imported }))
                  reloadMemory()
                } catch {
                  toastBus.error(t('settings.memoryImportFailed'))
                }
                e.target.value = ''
              }}
            />
          </label>
        </SettingsRow>
      </SettingsGroup>

      {/* R2-A: the entry list is gone. Two lists for the same inventory —
          here with 50 rows and a delete button, there in the panel with editing
          and a trash bin — were two half truths. The inventory now lives on one
          page, and this section shows what can be tuned about it. */}
      <SettingsGroup icon={ListChecks} title={t('settings.memoryGroupEntries')}>
        <SettingsRow
          icon={ListChecks}
          title={t('settings.memoryOpenPage')}
          description={t('settings.memoryOpenPageHint')}
          testid="memory-open-page"
        >
          <a
            href="#/memory"
            className="rounded-lg bg-brand/20 px-3 py-1.5 text-ui-xs font-medium text-brand-deep transition-colors hover:bg-brand/25 max-lg:min-h-11"
          >
            {t('settings.memoryOpenPage')}
          </a>
        </SettingsRow>
      </SettingsGroup>

      <SettingsGroup icon={Ban} title={t('settings.memoryGroupDanger')}>
        <SettingsRow
          icon={Ban}
          title={t('settings.clearMemory')}
          description={t('settings.clearMemoryHint')}
          testid="memory-clear"
        >
          {confirmClearMemory ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void clearMemoryAll()}
                className="rounded-lg border border-status-danger/30 bg-status-danger/20 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/30 max-lg:min-h-11"
              >
                {t('settings.confirmClear')}
              </button>
              <button
                type="button"
                onClick={() => setConfirmClearMemory(false)}
                className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/60 transition-colors glass-control hover:text-foreground max-lg:min-h-11"
              >
                {t('settings.cancel')}
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClearMemory(true)}
              className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors glass-control hover:bg-status-danger/10 hover:text-foreground max-lg:min-h-11"
            >
              {t('settings.clearMemory')}
            </button>
          )}
        </SettingsRow>
      </SettingsGroup>
    </div>
  )
}
