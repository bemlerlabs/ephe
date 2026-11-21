/**
 * Ephe — API client for the device folder (F2).
 *
 * `GET /api/device` answers the persistence declaration for this machine — every
 * entry the product says it keeps, what it holds, how many bytes it takes — and
 * `POST /api/device/forget` clears it through `core.persistence.forget`. Split
 * into its own module the way `artifacts.ts` was: the facade keeps the single
 * `@/lib/api` entry point, and the register's card reads only these two calls.
 */
import { request } from './http'

/** One declared entry as this folder holds it. */
export interface DeviceEntry {
  name: string
  kind: 'dir' | 'file' | 'socket'
  holds: string
  writer: string
  forgettable: boolean
  present: boolean
  bytes: number
}

export interface DeviceState {
  root: string
  declared: number
  present: number
  forgettable: number
  entries: DeviceEntry[]
  total_bytes: number
  /** The names the folder keeps that no row declares — never cleared, always shown. */
  unnamed: string[]
}

export interface DeviceForgetAnswer {
  removed: string[]
  kept: string[]
  unnamed: string[]
  root: string
  dry_run: boolean
}

/** What this device keeps, as the declaration reads the folder right now. */
export function getDeviceState(): Promise<DeviceState> {
  return request<DeviceState>('/api/device')
}

/**
 * Clear the device folder through the declaration.
 *
 * A run never unlinks anything unless the caller sends `dry_run: false` — the
 * promise the CLI verb keeps. The answer lists what went, what the declaration
 * keeps, and what it never named; the undeclared list is report-only.
 */
export function forgetDevice(
  body: { names?: string[]; dry_run?: boolean } = {},
): Promise<DeviceForgetAnswer> {
  return request<DeviceForgetAnswer>('/api/device/forget', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
