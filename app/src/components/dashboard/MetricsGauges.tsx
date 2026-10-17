/**
 * Ephe — Live Metrics Gauges (R26, mockup top bar)
 *
 * CPU % + sparkline, memory MB + bar, disk % + sparkline — polled from
 * GET /api/system/metrics (psutil backend, honest degradation: cpu/mem
 * render as "–" while available=false). Sparklines are dependency-free
 * inline SVG polylines over a small history ring buffer.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'
import { Cpu, MemoryStick, HardDrive } from 'lucide-react'
import { apiUrl } from '@/lib/api/http'

interface SystemMetrics {
  available: boolean
  cpu_percent: number | null
  mem_used_mb: number | null
  mem_percent: number | null
  disk_free_bytes: number
  disk_free_gb: number
  disk_percent: number
  uptime_s: number
}

const HISTORY = 24
const POLL_MS = 5000

/** Tiny dependency-free sparkline (SVG polyline over the last N values). */
export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const n = values.length
  if (n < 2) return <svg viewBox="0 0 48 14" className={className} aria-hidden="true" />
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(0.001, max - min)
  const pts = values
    .map((v, i) => `${(i / (n - 1)) * 48},${13 - ((v - min) / span) * 11 - 1}`)
    .join(' ')
  return (
    <svg viewBox="0 0 48 14" className={className} aria-hidden="true" preserveAspectRatio="none">
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** GB without floats like "1.0" — 1073741824 → "1 GiB" style short form. */
export function formatFree(
  bytes: number,
  t: (k: string, o?: Record<string, unknown>) => string,
): string {
  if (bytes <= 0) return t('metrics.freeZero')
  const gb = bytes / 1024 ** 3
  if (gb >= 1) return t('metrics.freeGb', { value: Math.round(gb) })
  return t('metrics.freeMb', { value: Math.round(bytes / 1024 ** 2) })
}

export function useSystemMetrics(): SystemMetrics | null {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null)
  useEffect(() => {
    let cancelled = false
    let id: number | null = null
    const load = async () => {
      try {
        const res = await fetch(apiUrl('/api/system/metrics'))
        if (!res.ok) return
        const data = (await res.json()) as SystemMetrics
        if (!cancelled) setMetrics(data)
      } catch {
        /* offline: keep last known gauges */
      }
    }
    // Poll only while the tab is visible: a hidden or minimised window must
    // not wake the psutil backend every 5s (CPU/battery, local-first).
    const start = () => {
      if (id !== null) return
      void load()
      id = window.setInterval(load, POLL_MS)
    }
    const stop = () => {
      if (id !== null) {
        window.clearInterval(id)
        id = null
      }
    }
    const onVisibility = () => (document.hidden ? stop() : start())
    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])
  return metrics
}

/** Ring-buffer history for sparklines, keeps pushing while mounted. */
function useHistory(value: number | null): number[] {
  const hist = useRef<number[]>([])
  const last = useRef<number | null>(null)
  if (value !== null && value !== last.current) {
    last.current = value
    hist.current = [...hist.current, value].slice(-HISTORY)
  }
  return hist.current
}

interface GaugeProps {
  metrics: SystemMetrics | null
}

export function MetricsGauges({ metrics }: GaugeProps) {
  const { t, i18n } = useTranslation()
  const cpuHist = useHistory(metrics?.cpu_percent ?? null)
  const diskHist = useHistory(metrics?.disk_percent ?? null)
  if (!metrics || !metrics.available) return null
  const pct = (v: number | null) => (v === null ? '–' : `${Math.round(v)}%`)
  return (
    <div
      className="hidden xl:flex items-center gap-3 text-ui-xs text-ink-faint"
      data-testid="metrics-gauges"
      role="status"
    >
      <span
        className="flex items-center gap-1"
        title={t('metrics.cpu')}
        aria-label={t('metrics.cpu')}
      >
        <Cpu className="h-3 w-3 text-brand/50" aria-hidden="true" />
        <span className="sr-only">{t('metrics.cpu')}</span>
        <span className="text-foreground/70 tabular-nums">{pct(metrics.cpu_percent)}</span>
        {/* DD-27: sparklines are decoration — they cost ~50px each and used to
            push the right header group over the nav buttons right at the xl
            boundary (1280px). Show the full treatment only where there is
            provable room (2xl), percentages everywhere. */}
        <span className="hidden 2xl:inline-flex items-center">
          <Sparkline values={cpuHist} className="h-3.5 w-12 text-brand/50" />
        </span>
      </span>
      <span
        className="flex items-center gap-1"
        title={t('metrics.mem')}
        aria-label={t('metrics.mem')}
      >
        <MemoryStick className="h-3 w-3 text-brand/50" aria-hidden="true" />
        <span className="sr-only">{t('metrics.mem')}</span>
        <span className="text-foreground/70 tabular-nums whitespace-nowrap">
          {metrics.mem_used_mb == null
            ? '–'
            : `${formatNumber(Math.round(metrics.mem_used_mb), i18n.language)} MB`}
        </span>
        <span
          aria-hidden="true"
          className="hidden 2xl:inline-block relative h-1 w-10 rounded-full bg-surface-raised overflow-hidden align-middle"
        >
          <span
            className="absolute inset-y-0 left-0 rounded-full bg-brand/70"
            style={{ width: `${Math.min(100, metrics.mem_percent ?? 0)}%` }}
          />
        </span>
      </span>
      <span
        className="flex items-center gap-1"
        title={t('metrics.disk')}
        aria-label={t('metrics.disk')}
      >
        <HardDrive className="h-3 w-3 text-brand/50" aria-hidden="true" />
        <span className="sr-only">{t('metrics.disk')}</span>
        <span className="text-foreground/70 tabular-nums">{pct(metrics.disk_percent)}</span>
        <span className="hidden 2xl:inline-flex items-center">
          <Sparkline values={diskHist} className="h-3.5 w-12 text-brand/50" />
        </span>
      </span>
    </div>
  )
}

export default MetricsGauges
