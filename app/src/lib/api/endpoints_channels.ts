/**
 * Endpoints: scheduler, memory depth, tasks, mobile, Telegram, Discord.
 * Moved 1:1 out of lib/api.ts (lines 608–840) — only the location changed, not the logic.
 */
import { BASE_URL, LAN_TOKEN, request } from './http'
import type {
  DiscordStatus,
  MemoryEntry,
  MemoryTrash,
  MigrateReport,
  MobileQR,
  ScheduleJob,
  SchedulePreset,
  ScheduleResult,
  TaskItem,
  TelegramDevice,
  TelegramPairing,
  TelegramStatus,
} from './types'

export function listSchedules(): Promise<{ jobs: ScheduleJob[] }> {
  return request<{ jobs: ScheduleJob[] }>('/api/schedule')
}

/** Without `limit` the server decides — `cron.history_rows` lives there. */
export function getScheduleResults(limit?: number): Promise<{ results: ScheduleResult[] }> {
  return request<{ results: ScheduleResult[] }>(
    `/api/schedule/results${limit === undefined ? '' : `?limit=${limit}`}`,
  )
}

/** R19: automation templates (offline index). */
export function getSchedulePresets(): Promise<{ presets: SchedulePreset[] }> {
  return request('/api/schedule/presets')
}

/** R19: run a job immediately (rerun) — the result lands in the history. */
export function runScheduleJob(jobId: string): Promise<ScheduleResult> {
  return request(`/api/schedule/${encodeURIComponent(jobId)}/run`, { method: 'POST' })
}

// ── R19: memory depth (list/search/delete/export/import) ─────────────────

export function listMemory(limit = 100): Promise<{ entries: MemoryEntry[]; total: number }> {
  return request(`/api/memory/list?limit=${limit}`)
}

export function searchMemory(
  q: string,
  topK = 10,
): Promise<{
  results: { id: string; text: string; metadata: Record<string, unknown>; score: number }[]
}> {
  return request(`/api/memory/search?q=${encodeURIComponent(q)}&top_k=${topK}`)
}

export function deleteMemoryEntry(id: string): Promise<{ deleted: string }> {
  return request(`/api/memory/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/** R40: edit instead of delete+re-add — the document ID and its metadata stay. */
export function updateMemoryEntry(id: string, text: string): Promise<{ updated: string }> {
  return request(`/api/memory/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
}

/** D3/D5: the same write style as the memory tool — a correction supersedes the
 * old fact instead of overwriting it (the lineage stays visible). */
export function supersedeMemoryEntry(
  id: string,
  text: string,
): Promise<{ stored: boolean; id: string }> {
  return request('/api/memory/store', {
    method: 'POST',
    body: JSON.stringify({ text, supersedes: id }),
  })
}

/** D5: the trash. In the archive, softly deleted facts; in the index always empty
 * (there, deletion is final — the empty list is the honest answer, and
 * `restore_supported` carries that with `detail` as its reason). */
export function listDeletedMemory(limit = 100): Promise<MemoryTrash> {
  return request(`/api/memory/deleted?limit=${limit}`)
}

/** D5: undo a forgetting. 404 when the entry is not in the trash. */
export function restoreMemoryEntry(id: string): Promise<{ restored: string }> {
  return request(`/api/memory/${encodeURIComponent(id)}/restore`, { method: 'POST' })
}

/** R2-A: which brain writes, and why it switched. */
export function setMemoryProvider(
  provider: 'kepta' | 'chroma',
): Promise<{ provider: string; reason: string; scope: string }> {
  return request('/api/memory/provider', {
    method: 'PUT',
    body: JSON.stringify({ provider }),
  })
}

/** R2-A: index→archive. First the dry run with numbers, then the button. */
export function migrateMemory(dryRun = true): Promise<MigrateReport> {
  return request('/api/memory/migrate', {
    method: 'POST',
    body: JSON.stringify({ dry_run: dryRun }),
  })
}

export function exportMemoryUrl(): string {
  const u = `${BASE_URL}/api/memory/export`
  return LAN_TOKEN ? `${u}?token=${encodeURIComponent(LAN_TOKEN)}` : u
}

export function importMemory(
  entries: { text: string; metadata?: Record<string, unknown> }[],
): Promise<{ imported: number; total: number }> {
  return request('/api/memory/import', { method: 'POST', body: JSON.stringify({ entries }) })
}

export async function createSchedule(
  task: string,
  cron?: string,
  delayMinutes?: number,
  maxRuns?: number,
): Promise<{ job_id: string; message: string }> {
  return request<{ job_id: string; message: string }>('/api/schedule', {
    method: 'POST',
    body: JSON.stringify({
      task,
      cron,
      delay_minutes: delayMinutes,
      max_runs: maxRuns,
    }),
  })
}

export function deleteSchedule(jobId: string): Promise<{ status: string; job_id: string }> {
  return request<{ status: string; job_id: string }>(`/api/schedule/${jobId}`, {
    method: 'DELETE',
  })
}

export function getTasks(): Promise<TaskItem[]> {
  return request<TaskItem[]>('/api/tasks')
}

export function updateTask(
  id: string,
  patch: Partial<Pick<TaskItem, 'status' | 'title' | 'project'>>,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/api/tasks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  })
}

export function deleteTask(id: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/api/tasks/${id}`, { method: 'DELETE' })
}

export function createTask(
  title: string,
  project?: string,
): Promise<{ success: boolean; id: string | null }> {
  return request('/api/tasks', { method: 'POST', body: JSON.stringify({ title, project }) })
}

export function getMobileQR(mode: 'auto' | 'lan' | 'public' = 'auto'): Promise<MobileQR> {
  return request<MobileQR>(`/api/mobile/qr?mode=${mode}`)
}

export function getMobileStatus(): Promise<{ connected: boolean }> {
  return request<{ connected: boolean }>('/api/mobile/status')
}

// ── Telegram-Channel (R24): QR-Pairing, Runner, Devices ─────────────────────

export function getTelegramStatus(): Promise<TelegramStatus> {
  return request<TelegramStatus>('/api/channels/telegram/status')
}

export function saveTelegramToken(token: string): Promise<{ mode: string; masked: string }> {
  return request<{ mode: string; masked: string }>('/api/channels/telegram/token', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export function deleteTelegramToken(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/api/channels/telegram/token', { method: 'DELETE' })
}

export function startTelegramChannel(): Promise<{ running: boolean }> {
  return request<{ running: boolean }>('/api/channels/telegram/start', { method: 'POST' })
}

export function stopTelegramChannel(): Promise<{ running: boolean }> {
  return request<{ running: boolean }>('/api/channels/telegram/stop', { method: 'POST' })
}

export function createTelegramPairing(): Promise<TelegramPairing> {
  return request<TelegramPairing>('/api/channels/telegram/pair', { method: 'POST' })
}

export function listTelegramDevices(): Promise<TelegramDevice[]> {
  return request<TelegramDevice[]>('/api/channels/telegram/devices')
}

export function revokeTelegramDevice(userId: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/channels/telegram/devices/${userId}`, { method: 'DELETE' })
}

// ── W3d: Discord channel (R24 pattern) ────────────────────────────────────────

export function getDiscordStatus(): Promise<DiscordStatus> {
  return request<DiscordStatus>('/api/channels/discord/status')
}

export function saveDiscordToken(token: string): Promise<{ mode: string; masked: string }> {
  return request<{ mode: string; masked: string }>('/api/channels/discord/token', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export function deleteDiscordToken(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/api/channels/discord/token', { method: 'DELETE' })
}

export function startDiscordChannel(): Promise<{ running: boolean }> {
  return request<{ running: boolean }>('/api/channels/discord/start', { method: 'POST' })
}

export function stopDiscordChannel(): Promise<{ running: boolean }> {
  return request<{ running: boolean }>('/api/channels/discord/stop', { method: 'POST' })
}
