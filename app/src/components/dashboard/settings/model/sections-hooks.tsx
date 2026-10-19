'use client'

/**
 * I6-4: the Hooks section — `core/user_hooks.py` was a real subsystem without a
 * surface.
 *
 * What is shown is what the core actually does: the one switch, the file it reads
 * from, per event its commands, and the recent runs from the audit log. Nothing
 * here writes hooks.json: a hook inherits the process rights of Ephe, so setting
 * one is a decision made on the device. And an event without a caller
 * (session_start, turn_end, pre_compact — `fire_event` has no production caller)
 * shows as "Events without a call site" instead of looking like an active hook.
 */
import { CircleSlash, FileCode2, Terminal } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { formatTime } from '@/lib/utils'
import { DeepFields } from './deepFields'
import type { HookEvent, HookSpec } from '@/lib/api'
import type { SettingsModel } from './types'

/** The events whose name tells the user something; unknown ones stay identifiers. */
const EVENT_ORDER = ['pre_tool', 'post_tool', 'session_start', 'turn_end', 'pre_compact']

function eventLabel(key: string, t: SettingsModel['t']): string {
  return EVENT_ORDER.includes(key) ? t(`settings.hooksEvent.${key}`) : key
}

function HookRow({ hook, event, t }: { hook: HookSpec; event: HookEvent; t: SettingsModel['t'] }) {
  return (
    <SettingsRow
      icon={Terminal}
      title={hook.command}
      description={
        event.live
          ? t('settings.hooksRowLive', {
              match: hook.match === '*' ? t('settings.hooksMatchAll') : hook.match,
              priority: hook.priority,
            })
          : t('settings.hooksRowDead', {
              match: hook.match === '*' ? t('settings.hooksMatchAll') : hook.match,
            })
      }
      testid={`hook-row-${event.key}-${hook.command.slice(0, 24)}`}
    />
  )
}

export function HooksSection({ model }: { model: SettingsModel }) {
  const { hooksLoading, hooksView, i18n, t } = model

  // D0-4: an event the server reports without any hook beside it, and a recent-run list
  // it omits, are both answers with nothing in them. Resolved here, once, so every row
  // below renders the empty state the area already has instead of the tab falling over.
  const events = [...(hooksView?.events ?? [])]
    .map((event) => ({ ...event, hooks: event.hooks ?? [] }))
    .sort((a, b) => EVENT_ORDER.indexOf(a.key) - EVENT_ORDER.indexOf(b.key))
  const recent = hooksView?.recent ?? []
  const live = events.filter((e) => e.live)
  const idle = events.filter((e) => !e.live)

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.hooksTitle')} subtitle={t('settings.hooksHint')} />

      <DeepFields model={model} prefixes={['hooks.']} />

      {hooksLoading && hooksView === null && (
        <p className="text-ui-xs text-ink-faint">{t('settings.hooksLoading')}</p>
      )}
      {!hooksLoading && hooksView === null && (
        <p className="text-ui-xs text-status-danger/80" data-testid="hooks-load-failed">
          {t('settings.hooksLoadFailed')}
        </p>
      )}

      {hooksView && (
        <>
          <SettingsGroup icon={FileCode2} title={t('settings.hooksGroupFile')}>
            <SettingsRow
              icon={FileCode2}
              title={hooksView.path}
              description={
                hooksView.exists ? t('settings.hooksFileExists') : t('settings.hooksFileMissing')
              }
              testid="hooks-file"
            />
          </SettingsGroup>

          {live.map((event, i) => (
            <SettingsGroup
              key={event.key ?? `unnamed-${i}`}
              icon={Terminal}
              title={eventLabel(event.key, t)}
              testid={`hooks-group-${event.key}`}
            >
              {event.hooks.length === 0 ? (
                <SettingsRow
                  icon={CircleSlash}
                  title={t('settings.hooksNoneTitle')}
                  description={t('settings.hooksNoneHint', {
                    event: eventLabel(event.key, t),
                  })}
                  testid={`hooks-empty-${event.key}`}
                />
              ) : (
                event.hooks.map((hook) => (
                  <HookRow key={hook.command} hook={hook} event={event} t={t} />
                ))
              )}
            </SettingsGroup>
          ))}

          {idle.length > 0 && (
            <SettingsGroup icon={CircleSlash} title={t('settings.hooksGroupIdle')}>
              {idle.map((event, i) => (
                <SettingsRow
                  key={event.key ?? `unnamed-${i}`}
                  icon={CircleSlash}
                  title={eventLabel(event.key, t)}
                  description={t('settings.hooksIdleHint', { count: event.hooks.length })}
                  testid={`hooks-idle-${event.key}`}
                />
              ))}
            </SettingsGroup>
          )}

          <SettingsGroup icon={Terminal} title={t('settings.hooksGroupRecent')}>
            {recent.length === 0 ? (
              <SettingsRow
                icon={CircleSlash}
                title={t('settings.hooksRecentEmpty')}
                description={t('settings.hooksRecentEmptyHint')}
                testid="hooks-recent-empty"
              />
            ) : (
              recent.map((run, i) => (
                <SettingsRow
                  key={`${run.ts}-${i}`}
                  icon={run.status === 'blocked' ? CircleSlash : Terminal}
                  title={t(`settings.hookStatus.${run.status}`, { defaultValue: run.status })}
                  description={[
                    formatTime(run.ts, i18n?.language),
                    run.detail
                      ? `${run.tool} · ${run.detail}`
                      : t('settings.hooksRunTool', { tool: run.tool }),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  testid={`hooks-recent-${i}`}
                />
              ))
            )}
          </SettingsGroup>
        </>
      )}
    </div>
  )
}
