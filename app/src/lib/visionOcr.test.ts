import { afterEach, describe, expect, it, vi } from 'vitest'
import { ocrImageText } from './visionOcr'

type Bridge = { __TAURI__?: unknown }

afterEach(() => {
  delete (window as Bridge).__TAURI__
})

describe('N7 — the shell reads the picture', () => {
  it('hands the data URL to the command and trims the answer', async () => {
    const invoke = vi.fn(async () => '  EPHE OCR TEST\n')
    ;(window as Bridge).__TAURI__ = { core: { invoke } }

    await expect(ocrImageText('data:image/png;base64,AA==')).resolves.toBe('EPHE OCR TEST')
    expect(invoke).toHaveBeenCalledWith('extract_image_text', {
      image: 'data:image/png;base64,AA==',
    })
  })

  it('answers null for an image without text', async () => {
    ;(window as Bridge).__TAURI__ = { core: { invoke: async () => '   ' } }
    await expect(ocrImageText('data:image/png;base64,AA==')).resolves.toBeNull()
  })

  it('answers null when the shell refuses the image', async () => {
    ;(window as Bridge).__TAURI__ = {
      core: {
        invoke: async () => {
          throw new Error('Vision OCR is a macOS feature in this build')
        },
      },
    }
    await expect(ocrImageText('data:image/png;base64,AA==')).resolves.toBeNull()
  })

  it('asks for nothing in a browser', async () => {
    await expect(ocrImageText('data:image/png;base64,AA==')).resolves.toBeNull()
  })
})
