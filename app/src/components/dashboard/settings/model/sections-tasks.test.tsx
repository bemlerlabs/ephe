// I7-3: the tasks section can create now, not only tick off — and the
// count in the header comes from the same list as the rows.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { renderTasks } from './sections-tasks'
import type { SettingsModel } from './types'
import type { TaskItem } from '@/lib/api/types'

const tasks: TaskItem[] = [
  { id: 'task-1', title: 'Zaun streichen', status: 'open', project: 'Haus' },
  { id: 'task-2', title: 'Steuer klären', status: 'done', project: null },
]

function model(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    handleTaskCreate: vi.fn(),
    handleTaskDelete: vi.fn(),
    handleTaskToggle: vi.fn(),
    setTaskDraft: vi.fn(),
    taskBusy: false,
    taskDraft: '',
    tasks,
    ...over,
  } as unknown as SettingsModel
}

describe('Aufgaben-Bereich (I7-3)', () => {
  it('Zahlen in der Titelzeile zählen dieselbe Liste wie die Zeilen', () => {
    render(renderTasks(model()))
    expect(screen.getByTestId('task-count-pill').textContent).toContain('"open":1')
    expect(screen.getByTestId('task-count-pill').textContent).toContain('"done":1')
    expect(screen.getByTestId('task-row-task-1')).toBeTruthy()
    expect(screen.getByTestId('task-row-task-2')).toBeTruthy()
  })

  it('Anlegen gibt den Titel weiter und die Gruppe erklärt die Datei', () => {
    const m = model({ taskDraft: 'Zaun streichen' })
    render(renderTasks(m))
    fireEvent.click(screen.getByTestId('task-create'))
    expect(m.handleTaskCreate).toHaveBeenCalled()
    expect(screen.getByTestId('tasks-group-new').textContent).toContain(
      'settings.tasksGroupNewHint',
    )
  })

  it('leere Eingabe legt nichts an', () => {
    const m = model({ taskDraft: '   ' })
    render(renderTasks(m))
    expect((screen.getByTestId('task-create') as HTMLButtonElement).disabled).toBe(true)
  })

  it('das Abhaken nennt seinen Zustand übersetzt, nicht als Rohwort', () => {
    render(renderTasks(model()))
    const toggle = screen.getByTestId('task-toggle-task-2') as HTMLElement
    expect(toggle.getAttribute('aria-label')).toContain('settings.taskToggle')
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(toggle.getAttribute('aria-label')).not.toMatch(/\b(done|open)\b/)
  })

  it('ein Projekt steht als Erklärung an der Zeile', () => {
    render(renderTasks(model()))
    expect(screen.getByTestId('task-row-task-1-desc').textContent).toContain('Haus')
    expect(screen.queryByTestId('task-row-task-2-desc')).toBeNull()
  })

  it('a completed task steps back without striking through its name', () => {
    render(renderTasks(model()))
    const open = screen.getByTestId('task-row-task-1').querySelector('p') as HTMLElement
    const done = screen.getByTestId('task-row-task-2').querySelector('p') as HTMLElement
    expect(done.className).toContain('text-ink-faint')
    expect(done.className).not.toContain('line-through')
    expect(open.className).toContain('text-ink')
    expect(open.className).not.toContain('text-ink-faint')
  })

  it('ohne Liste: Ladezeile, dann leerer Text — keine halbe Karte', () => {
    const loading = render(renderTasks(model({ tasks: null })))
    expect(loading.getByTestId('tasks-group-list').textContent).toContain('settings.loading')
    loading.unmount()
    const empty = render(renderTasks(model({ tasks: [] })))
    expect(empty.getByTestId('tasks-group-list').textContent).toContain('settings.noTasks')
    empty.unmount()
  })
})
