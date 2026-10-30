'use client'

import {
  FileBox,
  Layers,
  Loader2,
  MessageSquarePlus,
  Power,
  Puzzle,
  ShieldCheck,
  Trash2,
  Download,
} from 'lucide-react'
import { fileUrl } from '@/lib/api'
import { startDisposableChat } from '@/lib/chatSeed'
import { describeSkill } from '@/lib/slashCommands'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import SchedulerPanel from '../../SchedulerPanel'
import { DeepFields } from './deepFields'
import { SkillBuilderCard, SkillPackCard, skillGlyph } from './skillsStudio'
import type { SettingsModel } from './types'

export function renderSkills(model: SettingsModel) {
  const { handleSkillDelete, handleSkillToggle, packIndex, reloadSkills, skills, t } = model

  return (
    <div className="space-y-3">
      <PageHeader title={t('settings.skillsTitle')} subtitle={t('settings.skillsHint')} />

      <SkillBuilderCard t={t} onCreated={reloadSkills} />

      {/* R16 skill-pack management: install (zip/tgz) + refresh; W3b: URL install.
              I7-4: grouped with a purpose line, so every button says what it does
              to the file system. */}

      {/* R16: curated topic packs (offline index) — export as zip */}
      {packIndex && packIndex.length > 0 && (
        <SettingsGroup
          icon={Layers}
          title={t('settings.themedPacks')}
          description={t('settings.skillsGroupPacksHint')}
          testid="skills-group-packs"
        >
          <div className="space-y-2">
            {packIndex.map((pack) => (
              <SkillPackCard key={pack.id} pack={pack} t={t} />
            ))}
          </div>
        </SettingsGroup>
      )}

      <SettingsGroup
        icon={Puzzle}
        title={t('settings.skillsGroupMine')}
        description={t('settings.skillsGroupMineHint')}
        testid="skills-group-mine"
      >
        <div className="space-y-2 p-3">
          {skills === null ? (
            <Loader2 className="h-4 w-4 animate-spin text-brand/50" />
          ) : skills.length === 0 ? (
            <p className="text-ui-xs text-ink-faint">{t('settings.noSkills')}</p>
          ) : (
            skills.map((s) => {
              const Glyph = skillGlyph(s)
              return (
                <div
                  key={s.name}
                  className={`glass-reading rounded-xl p-3 ${s.disabled ? 'opacity-50' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <Glyph
                      className="h-[18px] w-[18px] shrink-0 text-brand/70"
                      strokeWidth={1.5}
                      aria-hidden="true"
                    />
                    <span className="text-ui-sm font-medium text-foreground/90">{s.name}</span>
                    {s.version && (
                      <span className="text-ui-xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft font-mono">
                        v{s.version}
                      </span>
                    )}
                    {s.is_builtin && (
                      <span className="text-ui-xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft">
                        {t('settings.skillBuiltinChip')}
                      </span>
                    )}
                    {s.install?.origin && (
                      <span
                        className="max-w-[16rem] truncate text-ui-xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft font-mono"
                        title={`${s.install.origin} · ${s.install.content_hash}`}
                        data-testid={`skill-origin-${s.name}`}
                      >
                        {s.install.origin}
                      </span>
                    )}
                    {s.unchanged === false && (
                      <span
                        className="text-ui-xs px-1.5 py-0.5 rounded-full bg-status-warning/20 text-status-warning"
                        data-testid={`skill-changed-${s.name}`}
                      >
                        {t('settings.skillsChangedChip')}
                      </span>
                    )}
                    {s.disabled && (
                      <span className="text-ui-xs px-1.5 py-0.5 rounded-full bg-status-danger/20 text-status-danger">
                        {t('settings.skillsDisabledChip')}
                      </span>
                    )}
                    <span className="flex-1" />
                    <button
                      type="button"
                      aria-label={
                        s.disabled ? t('settings.skillsEnable') : t('settings.skillsDisable')
                      }
                      onClick={() => void handleSkillToggle(s.name, !!s.disabled)}
                      className={`p-1.5 rounded-lg transition-colors ${s.disabled ? 'text-status-danger hover:bg-status-danger/20' : 'text-ink-faint hover:text-brand hover:bg-brand/10'}`}
                    >
                      <Power className="h-3.5 w-3.5" />
                    </button>
                    {!s.is_builtin && (
                      <button
                        type="button"
                        aria-label={t('settings.skillsDelete')}
                        onClick={() => void handleSkillDelete(s.name)}
                        className="p-1.5 rounded-lg text-ink-faint hover:text-status-danger hover:bg-status-danger/10 transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => startDisposableChat(s.trigger)}
                    data-testid={`skill-run-${s.name}`}
                    className="mt-1 inline-flex items-center gap-1.5 rounded-lg bg-surface px-2 py-1 text-ui-xs font-mono text-brand-deep transition-colors hover:bg-surface-interactive focus-ring"
                  >
                    <MessageSquarePlus className="h-3.5 w-3.5" strokeWidth={1.5} />
                    {s.trigger} · {t('settings.skillRunNow')}
                  </button>
                  <p className="text-ui-xs text-ink-soft mt-1">{describeSkill(s, t)}</p>
                  {s.install && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {s.unchanged !== false && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-status-success/15 px-1.5 py-0.5 text-ui-xs text-status-success">
                          <ShieldCheck className="h-3 w-3" strokeWidth={1.5} />
                          {t('settings.skillVerifiedRecipe')}
                        </span>
                      )}
                      <details className="text-ui-xs text-ink-faint">
                        <summary className="cursor-pointer">
                          {t('settings.skillProvenance')}
                        </summary>
                        <p
                          className="mt-1 break-all font-mono"
                          data-testid={`skill-hash-${s.name}`}
                        >
                          {s.install.origin} · {s.install.content_hash}
                        </p>
                      </details>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </SettingsGroup>
    </div>
  )
}

export function renderCron(model: SettingsModel) {
  const { handleScheduleCreate, handleScheduleDelete, scheduleJobs, t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.cronTitle')} subtitle={t('settings.cronHint')} />
      {/* I7-3: the four run controls of the schedule — read in core/scheduler.py */}
      <DeepFields model={model} prefixes={['cron.']} />
      <SchedulerPanel
        jobs={scheduleJobs}
        onCreate={handleScheduleCreate}
        onDelete={handleScheduleDelete}
      />
    </div>
  )
}

export function renderArtifacts(model: SettingsModel) {
  const { artifacts, t } = model

  return (
    <div className="space-y-3">
      <PageHeader title={t('settings.artifactsTitle')} subtitle={t('settings.artifactsSubtitle')} />
      {artifacts.length === 0 ? (
        <p className="text-ui-xs text-ink-faint">{t('settings.noArtifacts')}</p>
      ) : (
        artifacts.map((a) => {
          const name = a.path.split('/').pop() ?? a.path
          return (
            <div key={a.id} className="flex items-center gap-2 glass-reading rounded-xl px-3 py-2">
              <FileBox className="h-3.5 w-3.5 text-brand/70 shrink-0" />
              <span className="text-ui-xs text-foreground/70 truncate flex-1">{name}</span>
              <a
                href={fileUrl(a.path)}
                download
                aria-label={`${t('artifacts.download')}: ${name}`}
                className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground"
              >
                <Download className="h-3.5 w-3.5" />
              </a>
            </div>
          )
        })
      )}
    </div>
  )
}
