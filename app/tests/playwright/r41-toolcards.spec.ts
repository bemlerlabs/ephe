import { test, expect } from '@playwright/test'
import { writeFileSync, existsSync } from 'node:fs'
import { ensureOnboarded, gotoHash, hasDevHandle } from './helpers'

/**
 * Round 41 / reference-B parity (Z01–Z06): the tool-activity cards in the chat.
 * Dogfood: the DEV-only __epheStore handle fills an assistant message with real
 * tool calls; expected are the summary rows, the terminal block, the exit chip,
 * the diff stats, the checklist and the file opening in the preview panel.
 */
const PIN_FILE = '/tmp/ephe_r41_pin.md'
const PIN_DIFF = [
  '--- a/proj/README.md',
  '+++ b/proj/README.md',
  '@@ -1,2 +1,3 @@',
  ' # Projekt',
  '+## Kapitelein Neu',
  '-alte Zeile',
].join('\n')

test.describe('R41 — Tool-Karten im Chat-Stream', () => {
  test.beforeEach(async ({ page }) => {
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // only checkable once on the app page — about:blank naturally has no handle
    if (!(await hasDevHandle(page)))
      test.skip(true, 'braucht vite dev server (DEV-only __epheStore handle)')
  })

  test('Shell-, Edit- und Task-Familie rendern Summary + Details (Z01–Z06)', async ({ page }) => {
    if (!existsSync(PIN_FILE)) writeFileSync(PIN_FILE, '# Pin\n\nInhalt.\n')
    await page.evaluate(
      ({ cmdOut, diff }) => {
        const store = (
          window as unknown as {
            __epheStore: {
              getState: () => {
                createSession: (t?: string) => void
                addMessage: (r: 'assistant', c: string, t: unknown[]) => void
              }
            }
          }
        ).__epheStore.getState()
        store.createSession('R41 Karten-Session')
        store.addMessage('assistant', 'Ich habe gearbeitet.', [
          {
            id: 'c1',
            name: 'run_shell',
            args: { command: 'pnpm test' },
            result: cmdOut,
            status: 'completed',
          },
          {
            id: 'c2',
            name: 'edit_file',
            args: { path: '/tmp/proj/README.md' },
            result: diff,
            status: 'completed',
          },
          {
            id: 'c3',
            name: 'manage_tasks',
            args: { action: 'add', title: 'Beleg' },
            result: 'ok',
            status: 'completed',
          },
        ])
      },
      { cmdOut: 'alles gut\n[exit 3] fehlgeschlagen', diff: PIN_DIFF },
    )
    await page.waitForTimeout(400)

    // K3 click model: expand the summary row → card (shell/edit/write with
    // auto-open per the parity rule; the task body behind the details button).
    // Z01/Z02: shell card — human target in the summary, exit chip, output in the details
    await page.locator('[data-testid="tool-stream-row-shell"] button').first().click()
    const shellCard = page.locator('[data-testid="tool-card"][data-family="shell"]')
    await expect(shellCard.locator('[data-testid="tool-target"]')).toHaveText('pnpm test')
    await expect(shellCard.locator('[data-testid="tool-exit-chip"]')).toHaveText('exit 3')
    await expect(shellCard.locator('[data-testid="tool-cmdline"]')).toBeVisible()
    await expect(shellCard).toContainText('alles gut')
    // the stderr remainder behind the exit marker stays visible (judge finding, round-E repair)
    await expect(shellCard).toContainText('fehlgeschlagen')

    // Z03: edit card — base name + stats; the diff line is visible via auto-open
    await page.locator('[data-testid="tool-stream-row-edit"] button').first().click()
    const editCard = page.locator('[data-testid="tool-card"][data-family="edit"]')
    await expect(editCard.locator('[data-testid="tool-target"]')).toHaveText('README.md')
    await expect(editCard.locator('[data-testid="tool-stats"]')).toContainText('+1')
    await expect(editCard.locator('[data-testid="tool-stats"]')).toContainText('−1')
    await expect(editCard).toContainText('Kapitelein Neu')

    // Z06: task card — the checklist loads from the real /api/tasks list
    await page.locator('[data-testid="tool-stream-row-task"] button').first().click()
    const taskCard = page.locator('[data-testid="tool-card"][data-family="task"]')
    await expect(taskCard.locator('[data-testid="tool-target"]')).toHaveText('Beleg')
    await taskCard.getByRole('button', { name: /manage_tasks Details/ }).click()
    await expect(taskCard.locator('[data-testid="tool-task-list"]')).toBeVisible({ timeout: 8000 })
  })

  test('Open-in-Preview der Edit-Karte zeigt die /tmp-Datei gerendert (Z05)', async ({ page }) => {
    if (!existsSync(PIN_FILE)) writeFileSync(PIN_FILE, '# Pin\n\nInhalt.\n')
    await page.evaluate((p) => {
      const store = (
        window as unknown as {
          __epheStore: {
            getState: () => {
              createSession: (t?: string) => void
              addMessage: (r: 'assistant', c: string, t: unknown[]) => void
            }
          }
        }
      ).__epheStore.getState()
      store.createSession('R41 Vorschau-Session')
      store.addMessage('assistant', 'Neue Datei.', [
        {
          id: 'w1',
          name: 'write_file',
          args: { path: p, content: '# Pin\n\nInhalt.\n' },
          result: 'created',
          status: 'completed',
        },
      ])
    }, PIN_FILE)
    await page.waitForTimeout(400)
    // K3 click model: expand the write row → card with the Open-in-Preview button
    await page.locator('[data-testid="tool-stream-row-write"] button').first().click()
    const card = page.locator('[data-testid="tool-card"][data-family="write"]')
    await expect(card.locator('[data-testid="tool-target"]')).toHaveText('ephe_r41_pin.md')
    await card.locator('[data-testid="tool-open-preview"]').click()
    await expect(
      page.locator('[data-testid="file-preview-body"][data-kind="markdown"]'),
    ).toBeVisible({ timeout: 10000 })
  })
})
