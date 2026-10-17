/**
 * artifact-export.spec.ts — R17 acceptance: the Playwright export round trip.
 *
 * Drives the REAL dogfood stack (Vite 5173 + backend 8765): the deterministic
 * QR fast path produces a real PNG, the library registers it, and the
 * export endpoint returns a valid zip. Cleans up the entry + the file itself.
 */
import { expect, test } from '@playwright/test'

test('R17 Export-Roundtrip: Fast-Path-Artefakt → Bibliothek → zip', async ({ page, request }) => {
  // 1. The deterministic fast path: produce a QR code (intent /qr, no LLM needed)
  const stream = await request.post('/api/chat/stream', {
    data: { message: 'erstelle einen QR-Code für https://example.com/ephe-export-test' },
  })
  expect(stream.status()).toBe(200)
  const body = await stream.text()
  expect(body).toContain('file_result')

  // 2. The library has registered the artifact
  const list = await request.get('/api/artifacts', { params: { q: 'ephe_qr_code' } })
  expect(list.status()).toBe(200)
  const { artifacts } = await list.json()
  expect(artifacts.length).toBeGreaterThanOrEqual(1)
  const entry = artifacts[0]
  expect(entry.kind).toBe('png')

  // 3. The export endpoint returns a valid zip (PK magic) containing the artifact
  const zip = await request.get('/api/artifacts/export', { params: { ids: entry.id } })
  expect(zip.status()).toBe(200)
  expect(zip.headers()['content-type']).toBe('application/zip')
  const bytes = await zip.body()
  expect(bytes[0]).toBe(0x50) // 'P'
  expect(bytes[1]).toBe(0x4b) // 'K'

  // 4. UI: the library lists the artifact (the library entry lives in the header overflow)
  await page.goto('/#/chat', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  await page.click('[data-testid="header-more"]')
  await page.click('[data-testid="artifact-library-toggle"]')
  await page.waitForTimeout(1500)
  await expect(page.getByText(entry.name).first()).toBeVisible()

  // 5. Cleanup: the entry + the file (Downloads is an allowed root)
  const del = await request.delete(`/api/artifacts/${entry.id}`, {
    params: { delete_file: 'true' },
  })
  expect(del.status()).toBe(200)
  expect((await del.json()).file_removed).toBe(true)
})
