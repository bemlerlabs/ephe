/**
 * Skills Studio components: the pack preview that expands, the glyph per skill
 * family, and the builder that writes a skill through POST /api/skills.
 *
 * They live beside the section rather than inside it: the section is a render
 * function the settings panel calls on every pass, and the 400-line wall leaves no
 * room for two forms with their own state.
 */
import { useState } from 'react'
import {
  BarChart3,
  ChevronDown,
  Code2,
  Download,
  FileText,
  FlaskConical,
  Languages,
  Loader2,
  Map as MapIcon,
  Palette,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import { createSkill, exportPackUrl } from '@/lib/api'
import type { SkillPackInfo } from '@/lib/api/types'
import type { SettingsModel } from './types'

type T = SettingsModel['t']

/** A glyph per skill family, read from the name and the trigger. */
export function skillGlyph(skill: { name: string; trigger: string }): LucideIcon {
  const text = `${skill.name} ${skill.trigger}`.toLowerCase()
  if (/security|review|audit/.test(text)) return ShieldCheck
  if (/test|check|qa/.test(text)) return FlaskConical
  if (/code|refactor|debug|dev/.test(text)) return Code2
  if (/research|search|web|source/.test(text)) return Search
  if (/data|chart|analytic|metric/.test(text)) return BarChart3
  if (/design|image|svg|visual/.test(text)) return Palette
  if (/plan|roadmap|project/.test(text)) return MapIcon
  if (/translat|language|locale/.test(text)) return Languages
  if (/doc|writ|note|summar|email|pdf|deck|slide/.test(text)) return FileText
  return Sparkles
}

/** One curated pack; the first six skills are the preview, the rest is one click away. */
export function SkillPackCard({ pack, t }: { pack: SkillPackInfo; t: T }) {
  const [expanded, setExpanded] = useState(false)
  const hidden = Math.max(0, pack.skills.length - 6)
  const shown = expanded ? pack.skills : pack.skills.slice(0, 6)

  return (
    <div className="glass-reading rounded-xl p-3">
      <div className="flex items-center gap-2">
        <span className="text-ui-sm font-medium text-foreground/90">{pack.title}</span>
        <span
          data-testid={`pack-installed-${pack.id}`}
          className="text-ui-xs px-1.5 py-0.5 rounded-full bg-surface text-ink-soft tabular-nums"
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
        {shown.map((sk) => (
          <span
            key={sk.name}
            className="px-1.5 py-0.5 rounded-md bg-surface text-ink-soft text-ui-xs font-mono"
          >
            {sk.trigger || sk.name}
          </span>
        ))}
        {hidden > 0 && (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
            data-testid={`pack-expand-${pack.id}`}
            className="inline-flex items-center gap-1 rounded-md bg-surface px-1.5 py-0.5 text-ui-xs text-brand-deep transition-colors hover:bg-surface-interactive focus-ring"
          >
            <ChevronDown
              className={`h-3 w-3 transition-transform ${expanded ? 'rotate-180' : ''}`}
              strokeWidth={1.5}
            />
            {expanded ? t('settings.packShowLess') : t('settings.packShowAll', { count: hidden })}
          </button>
        )}
      </div>
    </div>
  )
}

/** The 30-second path from "what should Ephe remember" to an installed skill. */
export function SkillBuilderCard({ t, onCreated }: { t: T; onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState('')
  const [description, setDescription] = useState('')
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const ready = Boolean(name.trim() && trigger.trim() && description.trim() && prompt.trim())

  const submit = async () => {
    if (!ready || busy) return
    setBusy(true)
    setNote('')
    try {
      await createSkill({
        name: name.trim().replace(/^\/+/, ''),
        trigger: trigger.trim().startsWith('/') ? trigger.trim() : `/${trigger.trim()}`,
        description: description.trim(),
        system_prompt: prompt.trim(),
      })
      setName('')
      setTrigger('')
      setDescription('')
      setPrompt('')
      setNote(t('settings.skillBuilderCreated'))
      onCreated()
    } catch (err) {
      setNote(err instanceof Error && err.message ? err.message : t('settings.skillBuilderFailed'))
    } finally {
      setBusy(false)
    }
  }

  const field =
    'min-w-0 flex-1 rounded-lg bg-surface px-2 py-2 text-ui-input text-foreground/80 placeholder:text-ink-faint outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 max-lg:min-h-11'

  return (
    <SettingsGroup
      icon={Sparkles}
      title={t('settings.skillBuilderTitle')}
      description={t('settings.skillBuilderHint')}
      testid="skills-group-builder"
    >
      <div className="space-y-2 p-3">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          data-testid="skill-builder-toggle"
          className="flex items-center gap-1.5 rounded-lg bg-brand/15 px-3 py-2 text-ui-xs font-medium text-brand-deep transition-colors hover:bg-brand/20 focus-ring max-lg:min-h-11"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
            strokeWidth={1.5}
          />
          {t('settings.skillBuilderOpen')}
        </button>
        {open && (
          <div className="space-y-2">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                className={field}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('settings.skillBuilderName')}
                aria-label={t('settings.skillBuilderName')}
                data-testid="skill-builder-name"
              />
              <input
                className={field}
                value={trigger}
                onChange={(e) => setTrigger(e.target.value)}
                placeholder={t('settings.skillBuilderTrigger')}
                aria-label={t('settings.skillBuilderTrigger')}
                data-testid="skill-builder-trigger"
              />
            </div>
            <input
              className={`${field} w-full`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('settings.skillBuilderDescription')}
              aria-label={t('settings.skillBuilderDescription')}
              data-testid="skill-builder-description"
            />
            <textarea
              className={`${field} w-full`}
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t('settings.skillBuilderPrompt')}
              aria-label={t('settings.skillBuilderPrompt')}
              data-testid="skill-builder-prompt"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={!ready || busy}
                onClick={() => void submit()}
                data-testid="skill-builder-create"
                className="flex items-center gap-1.5 rounded-lg bg-brand/20 px-3 py-2 text-ui-xs font-medium text-brand-deep transition-colors disabled:opacity-50 max-lg:min-h-11"
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
                )}
                {t('settings.skillBuilderCreate')}
              </button>
              {note && (
                <p className="text-ui-xs text-ink-soft" role="status" data-testid="skill-builder-note">
                  {note}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </SettingsGroup>
  )
}
