'use client'

/**
 * I6-5: the Code execution area — the ceilings of the guest interpreter.
 *
 * Before, the card hung under Privacy, between the approval profile and the
 * Local-Data button, although it describes a runtime's time budget. And it was a
 * read-only card: `GET /api/settings/code-exec` returns exactly the values that
 * `core.cpython_cell.py` writes into the WASIConfig — report == enforced.
 *
 * Nothing is set here. The one value the kernel accepts is the fuel budget in raw
 * units (20,000,000,000); a number without a unit that nobody can set is not a dial.
 * The way out stays what it was: `EPHE_CODE_EXEC`, and every result names its runtime.
 */
import {
  CircleCheck,
  CircleX,
  Cpu,
  Database,
  FileText,
  GlobeLock,
  HardDrive,
  MemoryStick,
  ScrollText,
  Timer,
} from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import type { CodeExecPolicy } from '@/lib/api'
import type { SettingsModel } from './types'
import { fmtTokens } from '@/lib/format'

// Grouping follows the surface language, like every other number in the product
// (fmtTokens in lib/format). Fuel is an eleven-digit number, which is exactly why
// it must read the same way as the meter beside it.
const nf = (value: number, language?: string) => fmtTokens(value, language)
const human = (bytes: number) =>
  bytes >= 1048576 ? `${Math.round(bytes / 1048576)} MiB` : `${Math.round(bytes / 1024)} KiB`

/** The value on the right of the row — this card steers nothing, it measures. */
function Value({ text }: { text: string }) {
  return <span className="font-mono text-ui-xs text-foreground/80">{text}</span>
}

export function CodeExecSection({ model }: { model: SettingsModel }) {
  const { codeExecCfg, i18n, t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.codeExecAreaTitle')} subtitle={t('settings.codeExecHint')} />

      {!codeExecCfg ? (
        <LoadingRow label={t('settings.codeExecLoading')} data-testid="code-exec-loading" />
      ) : (
        <div className="space-y-4" data-testid="code-exec-policy">
          <SettingsGroup icon={Cpu} title={t('settings.codeExecGroupRuntime')}>
            <SettingsRow
              icon={codeExecCfg.runtime === 'kernel' ? CircleX : CircleCheck}
              title={codeExecCfg.runtime}
              description={t(
                codeExecCfg.runtime === 'kernel'
                  ? 'settings.codeExecRuntimeKernel'
                  : 'settings.codeExecRuntimeCell',
              )}
              testid="code-exec-runtime"
            />
            <SettingsRow
              icon={
                codeExecCfg.guest.entry_hash_ok && codeExecCfg.guest.stdlib_hash_ok
                  ? CircleCheck
                  : CircleX
              }
              title={t('settings.codeExecIntegrityTitle')}
              description={t(
                codeExecCfg.guest.entry_hash_ok && codeExecCfg.guest.stdlib_hash_ok
                  ? 'settings.codeExecIntegrityOk'
                  : 'settings.codeExecIntegrityBad',
              )}
              testid="code-exec-integrity"
            />
            <SettingsRow
              icon={Cpu}
              title={t('settings.codeExecGuest')}
              description={t('settings.codeExecGuestHint', {
                license: codeExecCfg.license.guest || '—',
              })}
              testid="code-exec-guest"
            >
              <Value text={`CPython ${codeExecCfg.guest.version}`} />
            </SettingsRow>
            <SettingsRow
              icon={FileText}
              title={t('settings.codeExecCellLicense')}
              description={t('settings.codeExecCellLicenseHint')}
              testid="code-exec-license"
            >
              <Value text={codeExecCfg.license.cell_runtime || '—'} />
            </SettingsRow>
            {codeExecCfg.guest.reason && (
              <SettingsRow
                icon={CircleX}
                title={t('settings.codeExecReasonTitle')}
                description={codeExecCfg.guest.reason}
                testid="code-exec-reason"
              />
            )}
          </SettingsGroup>

          <SettingsGroup icon={Timer} title={t('settings.codeExecGroupCeilings')}>
            <CeilingRows policy={codeExecCfg} t={t} language={i18n?.language} />
          </SettingsGroup>

          <SettingsGroup icon={GlobeLock} title={t('settings.codeExecGroupReach')}>
            <SettingsRow
              icon={GlobeLock}
              title={t('settings.codeExecNetwork')}
              description={t('settings.codeExecNetworkHint')}
              testid="code-exec-network"
            >
              <Value
                text={
                  codeExecCfg.network === 'none'
                    ? t('settings.codeExecNetworkNone')
                    : codeExecCfg.network
                }
              />
            </SettingsRow>
            <SettingsRow
              icon={HardDrive}
              title={t('settings.codeExecPreopens')}
              description={t('settings.codeExecPreopensHint')}
              testid="code-exec-preopens"
            >
              <Value text={codeExecCfg.preopens.join(' · ')} />
            </SettingsRow>
          </SettingsGroup>

          <p className="text-ui-xs text-ink-faint" data-testid="code-exec-optout">
            {t('settings.codeExecOptOut')}
          </p>
        </div>
      )}
    </div>
  )
}

function CeilingRows({
  policy,
  t,
  language,
}: {
  policy: CodeExecPolicy
  t: SettingsModel['t']
  language?: string
}) {
  const rows: Array<{
    key: string
    icon: typeof Timer
    title: string
    hint: string
    value: string
  }> = [
    {
      key: 'fuel',
      icon: Cpu,
      title: t('settings.codeExecFuel'),
      hint: t('settings.codeExecFuelHint'),
      value: nf(policy.max_fuel, language),
    },
    {
      key: 'memory',
      icon: MemoryStick,
      title: t('settings.codeExecMemory'),
      hint: t('settings.codeExecMemoryHint'),
      value: `${policy.max_memory_mb} MB`,
    },
    {
      key: 'timeout',
      icon: Timer,
      title: t('settings.codeExecTimeout'),
      hint: t('settings.codeExecTimeoutHint'),
      value: `${policy.timeout_seconds} s`,
    },
    {
      key: 'disk',
      icon: HardDrive,
      title: t('settings.codeExecDisk'),
      hint: t('settings.codeExecDiskHint'),
      value: human(policy.disk_quota_bytes),
    },
    ...(policy.work_quota_bytes
      ? [
          {
            key: 'work',
            icon: Database,
            title: t('settings.codeExecWorkQuota'),
            hint: t('settings.codeExecWorkQuotaHint'),
            value: human(policy.work_quota_bytes),
          },
        ]
      : []),
    {
      key: 'output',
      icon: ScrollText,
      title: t('settings.codeExecOutput'),
      hint: t('settings.codeExecOutputHint'),
      value: `${nf(policy.output_cap_bytes, language)} bytes`,
    },
    ...(policy.guest_forward_bytes && policy.guest_tee_cap_bytes
      ? [
          {
            key: 'journal',
            icon: ScrollText,
            title: t('settings.codeExecJournal'),
            hint: t('settings.codeExecJournalHint'),
            value: `${nf(policy.guest_forward_bytes, language)} live · ${nf(
              Math.round(policy.guest_tee_cap_bytes / 1024),
              language,
            )} KiB /work/stdout.log`,
          },
        ]
      : []),
  ]

  return (
    <>
      {rows.map((row) => (
        <SettingsRow
          key={row.key}
          icon={row.icon}
          title={row.title}
          description={row.hint}
          testid={`code-exec-${row.key}`}
        >
          <Value text={row.value} />
        </SettingsRow>
      ))}
    </>
  )
}
