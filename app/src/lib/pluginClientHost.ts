/**
 * The frame side of the page SDK.
 *
 * The sandboxed document posts one message per call. This module answers only
 * a message whose source is the frame it was given, and it calls the product
 * API with the app's own client. A lifecycle event for another bundle is dropped.
 */
import { ApiError, apiUrl, request } from './api/http'

export const SDK_CHANNEL = 'ephe.sdk'

const EVENT_NAMES = ['plugin.state', 'plugin.paused', 'plugin.mount'] as const

type SdkRequest = {
  channel?: string
  id?: string
  method?: string
  key?: string
  value?: unknown
  name?: string
  arguments?: Record<string, unknown>
}

type Frame = { contentWindow: Window | null }

function reply(frame: Frame, id: string, body: Record<string, unknown>) {
  frame.contentWindow?.postMessage({ channel: SDK_CHANNEL, id, ...body }, '*')
}

function belongs(pluginId: string, event: string, data: unknown): boolean {
  if (event === 'plugin.paused') return true
  if (!data || typeof data !== 'object') return false
  return (data as { name?: string }).name === pluginId
}

async function dispatch(pluginId: string, message: SdkRequest): Promise<unknown> {
  const id = encodeURIComponent(pluginId)
  if (message.method === 'storage.get') {
    return request<{ value: unknown; present: boolean }>(
      `/api/plugins/${id}/client/storage?key=${encodeURIComponent(String(message.key ?? ''))}`,
    )
  }
  if (message.method === 'storage.set') {
    return request<{ present: boolean }>(`/api/plugins/${id}/client/storage`, {
      method: 'PUT',
      body: JSON.stringify({ key: message.key, value: message.value ?? null }),
    })
  }
  if (message.method === 'tool.call') {
    return request<{ result: string }>(`/api/plugins/${id}/client/tool`, {
      method: 'POST',
      body: JSON.stringify({ name: message.name, arguments: message.arguments ?? {} }),
    })
  }
  throw new ApiError('unknown sdk method', 400, 'invalid_request')
}

export function attachPluginClient(
  frame: Frame,
  pluginId: string,
  onEvent?: (event: string, data: unknown) => void,
): () => void {
  let source: EventSource | null = null
  const onFrame = (raw: Event) => {
    if (!(raw instanceof MessageEvent)) return
    const event = raw as MessageEvent
    if (event.source !== frame.contentWindow) return
    const message = event.data as SdkRequest
    if (!message || message.channel !== SDK_CHANNEL || !message.id) return
    dispatch(pluginId, message).then(
      (result) => reply(frame, message.id as string, { ok: true, result }),
      (error: unknown) => {
        const coded = error instanceof ApiError ? error : null
        reply(frame, message.id as string, {
          ok: false,
          code: coded?.reasonCode || 'sdk_refused',
          message: coded?.message || 'refused',
        })
      },
    )
  }
  window.addEventListener('message', onFrame)

  if (typeof EventSource !== 'undefined') {
    try {
      source = new EventSource(apiUrl('/api/plugins/events'))
    } catch {
      source = null
    }
  }
  if (source) {
    for (const name of EVENT_NAMES) {
      source.addEventListener(name, (raw) => {
        let data: unknown = null
        try {
          data = JSON.parse((raw as MessageEvent).data)
        } catch {
          return
        }
        if (!belongs(pluginId, name, data)) return
        frame.contentWindow?.postMessage(
          { channel: SDK_CHANNEL, method: 'event', event: name, data },
          '*',
        )
        onEvent?.(name, data)
      })
    }
  }

  return () => {
    window.removeEventListener('message', onFrame)
    source?.close()
  }
}
