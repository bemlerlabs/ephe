'use client'

import { FileBox, Loader2, Download, Upload, Trash2, Power, Puzzle, Layers } from 'lucide-react'
import { exportPackUrl, fileUrl } from '@/lib/api'
import { describeSkill } from '@/lib/slashCommands'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import SchedulerPanel from '../../SchedulerPanel'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function renderSkills(model: SettingsModel) {
  const {
    fileInputRef,
    handleSkillDelete,
    handleSkillInstall,
    handleSkillInstallUrl,
    handleSkillToggle,
    packIndex,
    reloadSkills,
    setSkillUrl,
    skillUrl,
    skills,
    skillsBusy,
    skillsMsg,
    t,
  } = model

  return (
    <div className="space-y-3">
      <PageHeader title={t('settings.skillsTitle')} subtitle={t('settings.skillsHint')} />

      {/* R16 skill-pack management: install (zip/tgz) + refresh; W3b: URL install.
              I7-4: grouped with a purpose line, so every button says what it does
              to the file system. */}
      <SettingsGroup
        icon={Download}
        title={t('settings.skillsGroupInstall')}
        description={t('settings.skillsGroupInstallHint')}
        testid="skills-group-install"
      >
        <div className="space-y-2 p-3">
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,.tgz,.tar.gz,.tar"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void handleSkillInstall(f)
                e.target.value = ''
              }}
            />
            <button
              type="button"
              disabled={skillsBusy}
              onClick={() => fileInputRef.current?.click()}
              data-testid="skill-install-file"
              className="flex items-center gap-1.5 rounded-lg bg-brand/20 text-brand-deep hover:bg-brand/20 px-3 py-2 text-ui-xs font-medium transition-colors disabled:opacity-50 max-lg:min-h-11"
            >
              {skillsBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
              {t('settings.skillsInstall')}
            </button>
            <button
              type="button"
              onClick={reloadSkills}
              className="rounded-lg glass-control text-foreground/60 hover:text-foreground px-3 py-2 text-ui-xs font-medium transition-colors max-lg:min-h-11"
            >
              {t('settings.skillsRefresh')}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={skillUrl}
              onChange={(e) => setSkillUrl(e.target.value)}
              placeholder={t('settings.skillsInstallUrlPlaceholder')}
              aria-label={t('settings.skillsInstallUrl')}
              data-testid="skill-install-url-input"
              className="min-w-0 flex-1 rounded-lg bg-surface px-2 py-2 text-ui-input text-foreground/80 placeholder:text-ink-faint outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 focus:bg-surface transition-colors max-lg:min-h-11"
            />
            <button
              type="button"
              disabled={skillsBusy || !skillUrl.trim()}
              onClick={() => void handleSkillInstallUrl()}
              data-testid="skill-install-url"
              className="shrink-0 flex items-center gap-1.5 rounded-lg bg-brand/20 text-brand-deep hover:bg-brand/20 px-3 py-2 text-ui-xs font-medium transition-colors disabled:opacity-50 max-lg:min-h-11"
            >
              {skillsBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {t('settings.skillsInstallUrl')}
            </button>
          </div>
          {skillsMsg && <p className="text-ui-xs font-mono text-brand/80 break-all">{skillsMsg}</p>}
        </div>
      </SettingsGroup>

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
              <div key={pack.id} className="glass-reading rounded-xl p-3">
                <div className="flex items-center gap-2">
                  <span className="text-ui-sm font-medium text-foreground/90">{pack.title}</span>
                  <span
                    data-testid={`pack-installed-${pack.id}`}
                    className="text-ui-2xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft"
                  >
                    {t('settings.packInstalled', {
                      have: pack.skills.filter((sk) => sk.installed).length,
                      total: pack.skills.length,
                    })}
                  </span>
                  <span className="flex-1" />
                  <a
                    href={exportPackUrl(pack.id)}
                    download
                    data-testid={`pack-export-${pack.id}`}
                    className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-brand transition-colors"
                    aria-label={`${t('settings.exportPack')}: ${pack.title}`}
                  >
                    <Download className="h-3.5 w-3.5" />
                  </a>
                </div>
                <p className="text-ui-xs text-ink-soft mt-1">{pack.description}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {pack.skills.slice(0, 6).map((sk) => (
                    <span
                      key={sk.name}
                      className="px-1.5 py-0.5 rounded-md bg-surface text-ink-soft text-ui-xs font-mono"
                    >
                      {sk.trigger || sk.name}
                    </span>
                  ))}
                  {pack.skills.length > 6 && (
                    <span className="px-1.5 py-0.5 rounded-md bg-surface text-ink-faint text-ui-xs">
                      +{pack.skills.length - 6}
                    </span>
                  )}
                </div>
              </div>
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
            skills.map((s) => (
              <div
                key={s.name}
                className={`glass-reading rounded-xl p-3 ${s.disabled ? 'opacity-50' : ''}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-ui-sm font-medium text-foreground/90">{s.name}</span>
                  {s.version && (
                    <span className="text-ui-2xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft font-mono">
                      v{s.version}
                    </span>
                  )}
                  {s.is_builtin && (
                    <span className="text-ui-2xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft">
                      {t('settings.skillBuiltinChip')}
                    </span>
                  )}
                  {s.install?.origin && (
                    <span
                      className="max-w-[16rem] truncate text-ui-2xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft font-mono"
                      title={`${s.install.origin} · ${s.install.content_hash}`}
                      data-testid={`skill-origin-${s.name}`}
                    >
                      {s.install.origin}
                    </span>
                  )}
                  {s.unchanged === false && (
                    <span
                      className="text-ui-2xs px-1.5 py-0.5 rounded-full bg-status-warning/20 text-status-warning"
                      data-testid={`skill-changed-${s.name}`}
                    >
                      {t('settings.skillsChangedChip')}
                    </span>
                  )}
                  {s.disabled && (
                    <span className="text-ui-2xs px-1.5 py-0.5 rounded-full bg-status-danger/20 text-status-danger">
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
                <p className="text-ui-sm text-brand/60 font-mono mt-0.5">{s.trigger}</p>
                <p className="text-ui-xs text-ink-soft mt-1">{describeSkill(s, t)}</p>
              </div>
            ))
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
