'use client'

import { Check, ListTodo, X } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import type { SettingsModel } from './types'

export function renderTasks(model: SettingsModel) {
  const {
    handleTaskCreate,
    handleTaskDelete,
    handleTaskToggle,
    setTaskDraft,
    t,
    taskBusy,
    taskDraft,
    tasks,
  } = model
  const list = tasks ?? []
  const done = list.filter((x) => x.status === 'done').length

  return (
    <div className="space-y-3">
      <PageHeader
        title={t('settings.tasksTitle')}
        subtitle={t('settings.tasksHint')}
        actions={
          tasks === null ? undefined : (
            <span
              data-testid="task-count-pill"
              className="rounded-full bg-surface px-2.5 py-1 text-ui-xs font-medium text-ink-soft"
            >
              {t('settings.taskCounts', { open: list.length - done, done })}
            </span>
          )
        }
      />
      {/* I7-3: POST /api/tasks has existed since the first hour; this surface
              could only tick off and delete. Creating now lives here too. */}
      <SettingsGroup
        icon={ListTodo}
        title={t('settings.tasksGroupNew')}
        description={t('settings.tasksGroupNewHint')}
        testid="tasks-group-new"
      >
        <form
          className="flex items-center gap-2 p-3"
          onSubmit={(e) => {
            e.preventDefault()
            void handleTaskCreate()
          }}
        >
          <input
            type="text"
            value={taskDraft}
            onChange={(e) => setTaskDraft(e.target.value)}
            placeholder={t('settings.taskNewPlaceholder')}
            aria-label={t('settings.tasksGroupNew')}
            data-testid="task-new-input"
            className="min-w-0 flex-1 rounded-lg bg-surface px-3 py-2 text-ui-input text-foreground/80 placeholder:text-ink-faint outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 focus:bg-surface transition-colors max-lg:min-h-11"
          />
          <button
            type="submit"
            disabled={taskBusy || !taskDraft.trim()}
            data-testid="task-create"
            className="shrink-0 rounded-lg bg-brand/20 text-brand-deep hover:bg-brand/25 px-3 py-2 text-ui-xs font-medium transition-colors disabled:opacity-40 max-lg:min-h-11"
          >
            {t('settings.taskCreate')}
          </button>
        </form>
      </SettingsGroup>
      <SettingsGroup
        icon={Check}
        title={t('settings.tasksGroupList')}
        description={t('settings.tasksGroupListHint')}
        testid="tasks-group-list"
      >
        {tasks === null ? (
          <LoadingRow label={t('settings.loading')} className="p-3" />
        ) : list.length === 0 ? (
          <p className="p-3 text-ui-xs text-ink-faint">{t('settings.noTasks')}</p>
        ) : (
          list.map((task) => (
            <SettingsRow
              key={task.id}
              title={task.title}
              description={
                task.project ? `${t('settings.taskProject')}: ${task.project}` : undefined
              }
              muted={task.status === 'done'}
              testid={`task-row-${task.id}`}
            >
              <button
                type="button"
                role="checkbox"
                aria-checked={task.status === 'done'}
                aria-label={`${t('settings.taskToggle')}: ${task.title}`}
                onClick={() => void handleTaskToggle(task)}
                data-testid={`task-toggle-${task.id}`}
                className={`rounded-md border p-1 transition-colors focus-ring ${
                  task.status === 'done'
                    ? 'border-status-success/40 bg-status-success/10 text-status-success'
                    : 'border-hairline-strong text-transparent hover:border-hairline-strong'
                }`}
              >
                <Check className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => void handleTaskDelete(task.id)}
                aria-label={`${t('settings.deleteTask')}: ${task.title}`}
                data-testid={`task-delete-${task.id}`}
                className="rounded-lg p-1.5 text-ink-faint hover:bg-surface hover:text-status-danger transition-colors focus-ring"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </SettingsRow>
          ))
        )}
      </SettingsGroup>
    </div>
  )
}
