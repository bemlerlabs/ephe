/**
 * #93: the file a turn produced is reachable in the message that produced it.
 *
 * The rule lives in docs/AGENT_PANEL_CONDUCT_2026-10-11.md §4: the pane does not
 * open itself to show a result, so the result needs a way in where the user is
 * already looking. These tests hold both halves — what counts as a produced file,
 * and what the card may and may not offer for it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'
import MessageFileCard, { producedFiles } from './messageCard'
import { adoptWithTarget } from './adoptFlow'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ChatMessage } from '@/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))
vi.mock('./adoptFlow', () => ({ adoptWithTarget: vi.fn() }))

const openEvents: CustomEvent[] = []
function catchOpen() {
  const on = (e: Event) => openEvents.push(e as CustomEvent)
  window.addEventListener(PREVIEW_OPEN_EVENT, on)
  return () => window.removeEventListener(PREVIEW_OPEN_EVENT, on)
}

const msg = (over: Partial<ChatMessage> = {}): ChatMessage => ({
  id: 'm1',
  role: 'assistant',
  content: 'Done.',
  timestamp: Date.now(),
  ...over,
})

const pdfActivity = () =>
  msg({
    activities: [
      {
        id: 'a1',
        label: 'PDF: report.pdf',
        status: 'done',
        path: '/tmp/ephe/report.pdf',
        fileType: 'pdf',
        artifactId: 'art1',
      },
    ],
  })

beforeEach(() => {
  document.body.innerHTML = ''
  openEvents.length = 0
})
afterEach(cleanup)

describe('producedFiles', () => {
  it('reads a file_result off the activity it leaves behind', () => {
    const files = producedFiles(pdfActivity())
    expect(files).toHaveLength(1)
    expect(files[0]).toMatchObject({
      name: 'report.pdf',
      path: '/tmp/ephe/report.pdf',
      kind: 'pdf',
      artifactId: 'art1',
    })
  })

  it('takes a content-less artifact as a file and a code artifact as a listing', () => {
    const files = producedFiles(
      msg({
        artifacts: [
          {
            id: 'k1',
            artifact_type: 'file_pdf',
            content: '',
            language: 'text',
            title: 'plan.pdf',
            filename: '/tmp/ephe/plan.pdf',
          },
          {
            id: 'k2',
            artifact_type: 'code_other',
            content: 'print(1)',
            language: 'python',
            title: 'run.py',
            filename: '/tmp/ephe/run.py',
          },
        ],
      }),
    )
    expect(files.map((f) => f.name)).toEqual(['plan.pdf'])
  })

  it('names a file once when the activity and the artifact both carry it', () => {
    const m = pdfActivity()
    const twice = msg({
      activities: m.activities,
      artifacts: [
        {
          id: 'k1',
          artifact_type: 'file_pdf',
          content: '',
          language: 'text',
          title: 'report.pdf',
          filename: '/tmp/ephe/report.pdf',
        },
      ],
    })
    expect(producedFiles(twice)).toHaveLength(1)
  })

  it('keeps the arrival order of two files', () => {
    const files = producedFiles(
      msg({
        activities: [
          { id: 'a1', label: 'one.png', status: 'done', path: '/tmp/one.png', fileType: 'png' },
          { id: 'a2', label: 'two.pdf', status: 'done', path: '/tmp/two.pdf', fileType: 'pdf' },
        ],
      }),
    )
    expect(files.map((f) => f.name)).toEqual(['one.png', 'two.pdf'])
  })
})

describe('producer three — a tool call whose args name a path', () => {
  it('is covered for the artifact tools by the file_result, not by the args', () => {
    // create_pdf declares create_pdf(title, …, filename=…), so its args carry a bare
    // name while the bytes live under ~/.ephe/artifacts/<session>/. The server emits a
    // file_result with the absolute path for every result marker it recognises, so the
    // card reads the file from there. One card, absolute path — the bare name in the
    // args must not become a second row pointing at a 404.
    const files = producedFiles(
      msg({
        tool_calls: [
          {
            id: 't1',
            name: 'create_pdf',
            args: { title: 'Probe', filename: 'report.pdf' },
            result: 'PDF_FILE:/tmp/ephe/report.pdf\nPDF_PAGES:1',
            status: 'completed',
          },
        ],
        activities: [
          {
            id: 'a1',
            label: 'PDF: report.pdf',
            status: 'done',
            path: '/tmp/ephe/report.pdf',
            fileType: 'pdf',
            artifactId: 'art1',
          },
        ],
      }),
    )
    expect(files).toHaveLength(1)
    expect(files[0]!.path).toBe('/tmp/ephe/report.pdf')
  })

  it('stays with the tool card when the args name a workspace file', () => {
    // A write_file has no result marker, so no file_result and no card: its affordance
    // is the eye on its own card, which reaches the path the args name. Adding a row per
    // edited file would put a second control on every code edit beside its diff.
    const files = producedFiles(
      msg({
        tool_calls: [
          {
            id: 't2',
            name: 'write_file',
            args: { path: '/workspace/notes.md' },
            result: 'ok',
            status: 'completed',
          },
        ],
      }),
    )
    expect(files).toHaveLength(0)
  })
})

describe('MessageFileCard', () => {
  it('opens the file in the pane on the click, and only on the click', () => {
    const stop = catchOpen()
    render(<MessageFileCard file={producedFiles(pdfActivity())[0]!} />)
    expect(openEvents).toHaveLength(0)
    fireEvent.click(screen.getByTestId('message-file-open-act-a1'))
    expect(openEvents).toHaveLength(1)
    expect(openEvents[0]!.detail).toMatchObject({
      tab: 'preview',
      url: expect.stringContaining('/api/file?path='),
    })
    expect(String(openEvents[0]!.detail.url)).toContain('report.pdf')
    stop()
  })

  it('offers adopt only where the workbench knows the bytes', () => {
    const withId = producedFiles(pdfActivity())[0]!
    const { unmount } = render(<MessageFileCard file={withId} />)
    expect(screen.getByTestId('message-file-adopt-act-a1')).toBeTruthy()
    unmount()
    document.body.innerHTML = ''
    render(
      <MessageFileCard
        file={
          producedFiles(
            msg({ activities: [{ id: 'a9', label: 'x', status: 'done', path: '/tmp/x.pdf' }] }),
          )[0]!
        }
      />,
    )
    expect(screen.queryByTestId('message-file-adopt-act-a9')).toBeNull()
  })

  it('downloads through the artifact id when there is one', () => {
    render(<MessageFileCard file={producedFiles(pdfActivity())[0]!} />)
    const link = screen.getByTestId('message-file-download-act-a1')
    expect(link.getAttribute('href')).toContain('/api/artifacts/art1/file?download=1')
    expect(link.getAttribute('download')).toBe('report.pdf')
  })

  it('says there is no in-frame viewer instead of offering a white frame', async () => {
    vi.resetModules()
    vi.doMock('@/lib/desktopBaseUrl', async (importOriginal) => ({
      ...(await importOriginal<typeof import('@/lib/desktopBaseUrl')>()),
      IS_DESKTOP_SHELL: true,
    }))
    vi.doMock('react-i18next', () => ({
      useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
    }))
    const { default: DesktopCard } = await import('./messageCard')
    render(<DesktopCard file={producedFiles(pdfActivity())[0]!} />)
    expect(screen.queryByTestId('message-file-open-act-a1')).toBeNull()
    expect(screen.getByText('artifacts.preview.noViewer')).toBeTruthy()
    vi.doUnmock('@/lib/desktopBaseUrl')
  })
})

describe('the adopt failure names the next step', () => {
  it('keeps the alert and offers the retry that adopts again', async () => {
    const adopt = vi.mocked(adoptWithTarget)
    adopt.mockReset()
    adopt.mockRejectedValueOnce(new Error('disk full'))
    adopt.mockResolvedValueOnce({
      id: 'art1',
      adopted_path: '/x/report.pdf',
      state: 'current',
    } as never)
    render(<MessageFileCard file={producedFiles(pdfActivity())[0]!} />)
    fireEvent.click(screen.getByTestId('message-file-adopt-act-a1'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('artifacts.adoptFailed')
    const retry = screen.getByTestId('message-file-adopt-retry-act-a1')
    expect(retry.textContent).toBe('agentPanel.retry')
    fireEvent.click(retry)
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(adopt).toHaveBeenCalledTimes(2)
  })
})

describe('S17: the bytes the card points at', () => {
  const file = (over = {}) => ({
    key: 'k1',
    name: 'cat.png',
    path: '/tmp/ephe/cat.png',
    kind: 'png',
    artifactId: 'art-png',
    ...over,
  })

  it('renders an image inline through the artifact route, not /api/file', () => {
    render(<MessageFileCard file={file()} />)
    const img = screen.getByTestId('message-file-image-k1').querySelector('img')!
    expect(img.getAttribute('src')).toContain('/api/artifacts/art-png/file')
    expect(img.getAttribute('src')).not.toContain('/api/file?')
    expect(img.getAttribute('src')).not.toContain('download=1')
  })

  it('replaces a broken image with a reason and a retry that re-requests it', () => {
    render(<MessageFileCard file={file()} />)
    fireEvent.error(screen.getByTestId('message-file-image-k1').querySelector('img')!)
    expect(screen.getByTestId('message-file-unavailable-k1')).toBeTruthy()
    expect(screen.queryByTestId('message-file-image-k1')).toBeNull()
    fireEvent.click(screen.getByTestId('message-file-retry-k1'))
    const img = screen.getByTestId('message-file-image-k1').querySelector('img')!
    expect(img.getAttribute('src')).toContain('retry=1')
  })

  it('renders a PDF in a sandboxed frame', () => {
    render(<MessageFileCard file={file({ name: 'brief.pdf', kind: 'pdf', key: 'p1' })} />)
    const frame = screen.getByTestId('message-file-frame-p1')
    expect(frame.getAttribute('src')).toContain('/api/artifacts/art-png/file')
    expect(frame.getAttribute('src')).toContain('view=FitH')
    // A PDF stays unsandboxed: its viewer is an extension no sandboxed frame runs.
    expect(frame.getAttribute('sandbox')).toBeNull()
  })

  it('renders a video with controls and a range-capable source', () => {
    render(<MessageFileCard file={file({ name: 'clip.mp4', kind: 'video', key: 'v1' })} />)
    const video = screen.getByTestId('message-file-video-v1') as HTMLVideoElement
    expect(video.controls).toBe(true)
    expect(video.getAttribute('src')).toContain('/api/artifacts/art-png/file')
  })

  it('renders audio with controls', () => {
    render(<MessageFileCard file={file({ name: 'voice.mp3', kind: 'audio', key: 'a1' })} />)
    const audio = screen.getByTestId('message-file-audio-a1') as HTMLAudioElement
    expect(audio.controls).toBe(true)
  })
})
