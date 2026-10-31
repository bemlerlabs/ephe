/**
 * What a Discover card is allowed to do: enable, add, remove. Each action owns
 * one write to one store, and the sentence the page answers with.
 *
 * Split out of the page (the wall is 400 lines and the shelf plus the hero
 * already fills most of it). The page keeps what is shown; this keeps what
 * happens when a card is pressed.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  declareMcpEnv,
  disableSkill,
  enableSkill,
  installMarketPlan,
  planMarketInstall,
  putMcpSettings,
  setPluginEnabled,
} from '@/lib/api'
import { registrySpec } from './discoverNames'
import type { DiscoverItem, DiscoverSources } from './discoverModel'

export function useDiscoverActions(
  sources: DiscoverSources | null,
  indexSource: string,
  reload: () => Promise<void>,
) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [detail, setDetail] = useState<DiscoverItem | null>(null)

  const run = async (item: DiscoverItem, action: () => Promise<unknown>, done: string) => {
    setBusy(item.id)
    setNotice('')
    try {
      await action()
      setNotice(t('discover.did', { name: item.title, what: t(done) }))
      await reload()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : t('discover.didNot', { name: item.title }))
    } finally {
      setBusy('')
    }
  }

  /** A skill has its own pair of routes; a connector lives in the MCP server list. */
  const onToggle = (item: DiscoverItem, next: boolean) => {
    if (item.kind === 'skill') {
      return run(
        item,
        () => (next ? enableSkill(item.name) : disableSkill(item.name)),
        next ? 'discover.stateOn' : 'discover.stateOff',
      )
    }
    if (item.kind === 'connector') {
      if (!item.spec) {
        setNotice(t('discover.didNot', { name: item.title }))
        return undefined
      }
      const servers = (sources?.mcp?.servers ?? []).filter((one) => one !== item.spec)
      return run(
        item,
        () => putMcpSettings(next ? [...servers, item.spec as string] : servers),
        next ? 'discover.stateOn' : 'discover.stateOff',
      )
    }
    return run(
      item,
      () => setPluginEnabled(item.name, next),
      next ? 'discover.stateOn' : 'discover.stateOff',
    )
  }

  const onAdd = (item: DiscoverItem) => {
    if (item.kind === 'connector') {
      const spec = item.spec ?? (item.installHint ? registrySpec(item.installHint) : null)
      if (!spec) {
        // A catalogue line with a `<folder>` placeholder needs an argument no
        // list can invent; saying which line is the honest answer.
        setNotice(
          item.installHint && /<[^>]+>/.test(item.installHint)
            ? t('discover.needsArgument', { name: item.title })
            : t('discover.didNot', { name: item.title }),
        )
        return undefined
      }
      const current = sources?.mcp?.servers ?? []
      const names = (item.requiredEnv ?? []).map((one) => one.name)
      return run(
        item,
        async () => {
          await putMcpSettings(current.includes(spec) ? current : [...current, spec])
          // The entry stands without the declaration; a refusal here must not
          // report the add as failed after its first write landed.
          if (names.length) await declareMcpEnv(spec, names).catch(() => undefined)
        },
        'discover.added',
      )?.then(() => {
        // A connector that declared a key cannot start without one, so the sheet
        // that takes it opens right after the add instead of leaving a dead entry.
        if (names.length) setDetail({ ...item, installed: true, spec })
      })
    }
    if (item.kind === 'skill') {
      return run(item, () => enableSkill(item.name), 'discover.added')
    }
    return run(
      item,
      async () => {
        const plan = await planMarketInstall(indexSource, item.name, item.version ?? '')
        if (plan.status === 'refused')
          throw new Error(plan.error || plan.code || t('discover.refused'))
        return installMarketPlan(plan)
      },
      'discover.added',
    )
  }

  const onRemove = (item: DiscoverItem) => {
    if (item.kind === 'connector') {
      const current = sources?.mcp?.servers ?? []
      // Remove the exact line this row rides on — a name comparison collapsed
      // every `/mcp` endpoint into one and removed the wrong servers.
      const next = item.spec ? current.filter((one) => one !== item.spec) : current
      return run(item, () => putMcpSettings(next), 'discover.removed')
    }
    return run(item, () => setPluginEnabled(item.name, false), 'discover.removed')
  }

  return { busy, notice, detail, setDetail, onToggle, onAdd, onRemove }
}
