import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import DiffView, { parseUnifiedDiff } from '@/components/dashboard/DiffView'
import { gitApplyPatch } from '@/lib/api'

// W16/P1: DiffView grows from a pure colour-coded line stream into an interactive
// hunk viewer: `@@ -l,s +l,s @@` parsing, per hunk "Übernehmen" (git apply // language-gate: ignore — "Übernehmen" is the German button label the UI renders, locales/de.json common.apply
// --cached) and "Verwerfen" (git apply -R) through /api/git/apply. // language-gate: ignore — "Verwerfen" is the German button label the UI renders, locales/de.json common.discard

vi.mock('@/lib/api', () => ({
  gitApplyPatch: vi.fn(async () => ({ ok: true })),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const TWO_HUNK_DIFF = [
  'diff --git a/app.py b/app.py',
  'index 1111111..2222222 100644',
  '--- a/app.py',
  '+++ b/app.py',
  '@@ -1,3 +1,3 @@',
  ' line 1',
  '-line 2',
  '+line 2 edited',
  ' line 3',
  '@@ -8,3 +8,3 @@',
  ' line 8 before',
  '-line 8',
  '+line 8 edited',
  ' line 10',
].join('\n')

describe('parseUnifiedDiff (W16)', () => {
  it('splits a 2-hunk diff into single hunks with complete patches', () => {
    const hunks = parseUnifiedDiff(TWO_HUNK_DIFF, 'app.py')
    expect(hunks).toHaveLength(2)
    expect(hunks[0]!.header).toBe('@@ -1,3 +1,3 @@')
    expect(hunks[1]!.header).toBe('@@ -8,3 +8,3 @@')
    // Hunk 1's patch contains the file header + the first hunk, NOT the second
    expect(hunks[0]!.patch).toContain('--- a/app.py')
    expect(hunks[0]!.patch).toContain('@@ -1,3 +1,3 @@')
    expect(hunks[0]!.patch).toContain('+line 2 edited')
    expect(hunks[0]!.patch).not.toContain('@@ -8,3 +8,3 @@')
    expect(hunks[1]!.patch).toContain('+line 8 edited')
    expect(hunks[1]!.patch).not.toContain('+line 2 edited')
  })

  it('synthesizes a file header when the diff holds only raw hunks (edit_file form)', () => {
    const raw = '@@ -1,2 +1,2 @@\n alt\n-weg\n+neu'
    const hunks = parseUnifiedDiff(raw, 'src/x.ts')
    expect(hunks).toHaveLength(1)
    expect(hunks[0]!.patch).toContain('--- a/src/x.ts')
    expect(hunks[0]!.patch).toContain('+++ b/src/x.ts')
    expect(hunks[0]!.patch).toContain('+neu')
  })

  it('returns [] for diffs without a hunk header', () => {
    expect(parseUnifiedDiff('nur text\nkeine hunks')).toEqual([])
  })
})

describe('DiffView hunk actions (W16)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // P0-1: discard is confirm-gated; jsdom's confirm is falsy by default, so
    // opt in explicitly per test that expects the destructive path to run.
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders an apply and a discard button per hunk', () => {
    render(<DiffView diff={TWO_HUNK_DIFF} filePath="app.py" />)
    expect(screen.getByTestId('hunk-apply-0')).toBeTruthy()
    expect(screen.getByTestId('hunk-discard-0')).toBeTruthy()
    expect(screen.getByTestId('hunk-apply-1')).toBeTruthy()
    expect(screen.getByTestId('hunk-discard-1')).toBeTruthy()
  })

  it('apply stages exactly the chosen hunk (git apply --cached)', async () => {
    render(<DiffView diff={TWO_HUNK_DIFF} filePath="app.py" />)
    await act(async () => {
      fireEvent.click(screen.getByTestId('hunk-apply-1'))
    })
    expect(gitApplyPatch).toHaveBeenCalledTimes(1)
    const [patch, opts] = vi.mocked(gitApplyPatch).mock.calls[0]!
    expect(opts).toEqual({ staged: true })
    expect(patch).toContain('@@ -8,3 +8,3 @@')
    expect(patch).not.toContain('@@ -1,3 +1,3 @@')
  })

  it('discard reverse-applies the chosen hunk (git apply -R)', async () => {
    render(<DiffView diff={TWO_HUNK_DIFF} filePath="app.py" />)
    await act(async () => {
      fireEvent.click(screen.getByTestId('hunk-discard-0'))
    })
    const [patch, opts] = vi.mocked(gitApplyPatch).mock.calls[0]!
    expect(opts).toEqual({ reverse: true })
    expect(patch).toContain('@@ -1,3 +1,3 @@')
    expect(patch).not.toContain('@@ -8,3 +8,3 @@')
  })

  it('P0-1: discard is confirm-gated and without a confirmation no git apply runs', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<DiffView diff={TWO_HUNK_DIFF} filePath="app.py" />)
    fireEvent.click(screen.getByTestId('hunk-discard-0'))
    expect(window.confirm).toHaveBeenCalledTimes(1)
    expect(gitApplyPatch).not.toHaveBeenCalled()
  })

  it('P0-1: apply calls onApplied after success (the refresh loop)', async () => {
    const onApplied = vi.fn()
    render(<DiffView diff={TWO_HUNK_DIFF} filePath="app.py" onApplied={onApplied} />)
    await act(async () => {
      fireEvent.click(screen.getByTestId('hunk-apply-0'))
    })
    expect(onApplied).toHaveBeenCalledTimes(1)
  })

  it('without filePath and file header hunks stay informative and show no buttons', () => {
    render(<DiffView diff={TWO_HUNK_DIFF} />)
    expect(screen.queryByTestId('hunk-apply-0')).toBeNull()
    expect(screen.queryByTestId('hunk-discard-0')).toBeNull()
  })

  it('the colouring holds: plus lines green, minus lines red', () => {
    render(<DiffView diff={TWO_HUNK_DIFF} filePath="app.py" />)
    // P1-1: lines consist of word-level segment spans → match with a function
    // against the accumulated textContent (as recommended by testing-library).
    const added = screen.getByText((_c, el) => el?.textContent === '+line 2 edited')
    const removed = screen.getByText((_c, el) => el?.textContent === '-line 2')
    expect(added.className).toContain('text-status-success')
    expect(removed.className).toContain('text-status-danger')
  })
})
