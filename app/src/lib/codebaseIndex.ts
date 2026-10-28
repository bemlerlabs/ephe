import { apiUrl } from '@/lib/api'

export interface CodebaseIndexStatus {
  state: 'idle' | 'indexing' | 'ready' | 'error'
  files: number
  symbols: number
  indexed: number
  total: number
  error?: string | null
  duration_ms?: number
}

const EMPTY: CodebaseIndexStatus = {
  state: 'idle',
  files: 0,
  symbols: 0,
  indexed: 0,
  total: 0,
}

async function readStatus(response: Response): Promise<CodebaseIndexStatus> {
  if (!response.ok) throw new Error(`index status HTTP ${response.status}`)
  const body = (await response.json()) as Partial<CodebaseIndexStatus>
  return { ...EMPTY, ...body }
}

export async function fetchIndexStatus(): Promise<CodebaseIndexStatus> {
  return readStatus(await fetch(apiUrl('/api/project/index/status')))
}

export async function startIndex(): Promise<CodebaseIndexStatus> {
  return readStatus(
    await fetch(apiUrl('/api/project/index'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }),
  )
}

export function indexProgress(status: CodebaseIndexStatus): number {
  if (status.state === 'ready') return 100
  if (status.total <= 0) return 0
  return Math.min(100, Math.round((status.indexed / status.total) * 100))
}
