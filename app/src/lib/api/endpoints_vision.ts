/**
 * Vision bindings (W4): image analysis through the engine the user chose.
 *
 * A chat turn can carry an image too (the agent's analyze_image tool). These
 * bindings feed the standalone tools surface, where one image is analysed on
 * its own without a session.
 *   POST /api/vision/analyze — multipart upload
 *   POST /api/vision/base64  — base64 body, for a caller that cannot use FormData
 */
import { BASE_URL, LAN_TOKEN, request } from './http'

export interface VisionAnalysis {
  analysis: string
  filename: string
  image_url: string
  model: string
  question: string
}

const DEFAULT_QUESTION = 'Describe this image in detail.'

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra }
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  return headers
}

/** Upload an image and analyse it with the active engine. */
export async function analyzeImage(
  file: File | Blob,
  question: string = DEFAULT_QUESTION,
  model = '',
): Promise<VisionAnalysis> {
  const form = new FormData()
  form.append('file', file, file instanceof File ? file.name : 'upload.png')
  form.append('question', question)
  // Only a chosen tag travels; an empty one would read as an explicit model.
  if (model) form.append('model', model)
  const res = await fetch(`${BASE_URL}/api/vision/analyze`, {
    method: 'POST',
    body: form,
    headers: authHeaders(),
  })
  return readAnalysis(res)
}

/** Analyse an image handed in as a base64 string. */
export function analyzeImageBase64(
  imageB64: string,
  question: string = DEFAULT_QUESTION,
  model = '',
): Promise<VisionAnalysis> {
  const body: Record<string, string> = { image_b64: imageB64, question }
  if (model) body.model = model
  return request<VisionAnalysis>('/api/vision/base64', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

async function readAnalysis(res: Response): Promise<VisionAnalysis> {
  if (!res.ok) {
    let detail = `API ${res.status}: ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: string; error?: { message?: string } }
      detail = body.error?.message || body.detail || detail
    } catch {
      /* body was not JSON — the status line stays */
    }
    throw new Error(detail)
  }
  return (await res.json()) as VisionAnalysis
}
