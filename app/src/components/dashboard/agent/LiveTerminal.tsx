/**
 * LiveTerminal — an interactive full-PTY terminal (P1-5).
 *
 * xterm.js in the panel, fed by the persistent backend PTY over a WebSocket
 * (/api/shell/term). Raw keystrokes go to the PTY as {"type":"input"} — echo, line
 * editing, Ctrl-C (SIGINT) and full-screen apps (vim/less) are handled natively by
 * the shell's line discipline. A resize reports cols/rows (→ SIGWINCH).
 *
 * Session continuity: the backend PTY lives process-wide; this component is only a
 * viewer. Switching tabs or closing the panel disconnects the WS but does NOT kill
 * the shell — on reconnect the scrollback replay (server side) comes back.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Terminal, type ITheme } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { wsUrl } from '@/lib/api'

type Conn = 'connecting' | 'open' | 'closed'

/**
 * N1: the terminal well reads the sheet instead of carrying colours of its own.
 *
 * The background was a dead near-black that globals.css names as the wrong ink
 * ground — the ink ground is "warm, not dead black" — and the cursor wore a
 * Tailwind green that appears nowhere in the palette, beside a neutral grey in a
 * warm product. Those four values made LiveTerminal the third-largest raw-colour
 * cluster in app/src (scripts/design_tokens_check.mjs). The role names below are
 * the ones body{} paints with, so the well follows the theme like every other
 * surface: the sheet is the only source, and no value here is written down.
 */
function readWell(): ITheme {
  const root = getComputedStyle(document.documentElement)
  // No fallbacks on purpose: a fallback is a value of its own, and the point is
  // that none is written here. A token that does not resolve leaves the slot out
  // and xterm's own default stands.
  const slots: [string, string][] = [
    ['background', '--surface-base'],
    ['foreground', '--text-role-primary'],
    ['cursor', '--color-brand'],
    ['selectionBackground', '--color-brand-tint'],
  ]
  const theme: ITheme = {}
  for (const [slot, token] of slots) {
    const value = root.getPropertyValue(token).trim()
    if (value) (theme as Record<string, string>)[slot] = value
  }
  return theme
}

export default function LiveTerminal({ className }: { className?: string }) {
  const { t } = useTranslation()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [conn, setConn] = useState<Conn>('connecting')

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)',
      fontSize: 13,
      theme: readWell(),
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(host)
    try {
      fit.fit()
    } catch {
      /* the host has no size yet (the panel animates in) — ResizeObserver corrects it. */
    }

    let ws: WebSocket | null = null
    let disposed = false
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0

    const sendResize = () => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    }

    const connect = () => {
      if (disposed) return
      setConn('connecting')
      ws = new WebSocket(wsUrl('/api/shell/term'))
      ws.onopen = () => {
        if (disposed) return
        attempt = 0
        setConn('open')
        sendResize()
        term.focus()
      }
      ws.onmessage = (ev) => {
        try {
          const frame = JSON.parse(String(ev.data)) as {
            type: string
            data?: string
            code?: number
          }
          if (frame.type === 'output' && typeof frame.data === 'string') term.write(frame.data)
          else if (frame.type === 'exit')
            term.write(`\r\n\x1b[2m[shell exited (code ${frame.code ?? 0})]\x1b[0m\r\n`)
        } catch {
          /* ignore non-JSON frames. */
        }
      }
      ws.onclose = () => {
        if (disposed) return
        setConn('closed')
        // backoff reconnect as long as the panel lives (continuity is server-side).
        attempt += 1
        const delay = Math.min(1000 * 2 ** (attempt - 1), 8000)
        reconnectTimer = setTimeout(connect, delay)
      }
      ws.onerror = () => ws?.close()
    }

    const dataDisp = term.onData((d) => {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data: d }))
    })

    const ro = new ResizeObserver(() => {
      try {
        fit.fit()
      } catch {
        /* zero-size transient */
      }
      sendResize()
    })
    ro.observe(host)

    // N1: the well follows a theme switch while the pane is open. The values are
    // resolved once, so flipping the class on <html> would otherwise leave the
    // terminal painted in the previous theme's ground.
    const themeWatch = new MutationObserver(() => {
      term.options.theme = readWell()
    })
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

    connect()

    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      themeWatch.disconnect()
      ro.disconnect()
      dataDisp.dispose()
      // close the WS (do not kill it) — the backend PTY stays alive for a reconnect.
      if (ws && ws.readyState <= WebSocket.OPEN) ws.close()
      term.dispose()
    }
  }, [])

  return (
    <div
      className={className}
      data-testid="live-terminal"
      style={{ position: 'relative', height: '100%' }}
    >
      <div ref={hostRef} style={{ position: 'absolute', inset: 0 }} />
      {conn !== 'open' && (
        <div className="absolute top-2 right-2 z-10 text-ui-2xs font-mono px-1.5 py-0.5 rounded bg-canvas/60 text-ink-soft pointer-events-none">
          {conn === 'connecting'
            ? t('agentPanel.terminalConnecting')
            : t('agentPanel.terminalReconnecting')}
        </div>
      )}
    </div>
  )
}
