import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LandingSection } from './LandingSection'
import { INSTALL_COMMAND, INSTALL_VERSION, REPO_BLOB, WINDOWS_COMMAND } from './landingFacts'

type CopyState = 'idle' | 'copied' | 'failed'

/**
 * The install step. The command is the README's, built from the version this tree
 * carries, and the copy button is the only stateful thing on the page: a refused
 * clipboard is reported instead of leaving the click silent.
 */
export function LandingTryIt() {
  const { t } = useTranslation()
  const [copy, setCopy] = useState<CopyState>('idle')

  const onCopy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('no clipboard')
      await navigator.clipboard.writeText(INSTALL_COMMAND)
      setCopy('copied')
    } catch {
      setCopy('failed')
    }
  }

  return (
    <LandingSection
      id="landing-install"
      eyebrow={t('landing.install.eyebrow')}
      title={t('landing.install.title')}
      lede={t('landing.install.lede', { version: INSTALL_VERSION })}
    >
      <div className="max-w-3xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-ui-2xs uppercase tracking-[0.14em] text-ink-faint">
            {t('landing.install.macosLinux')}
          </p>
          <button
            type="button"
            data-testid="landing-install-copy"
            onClick={onCopy}
            className="focus-ring glass-control inline-flex h-10 items-center justify-center rounded-xl px-4 text-ui-sm font-medium text-foreground transition-colors duration-fast hover:bg-brand/10"
          >
            {t('landing.install.copy')}
          </button>
        </div>
        <pre
          tabIndex={0}
          className="mt-2 overflow-x-auto rounded-xl border border-hairline bg-surface/40 px-3 py-2.5 font-mono text-ui-xs break-words whitespace-pre-wrap text-foreground sm:whitespace-pre"
        >
          <code data-testid="landing-install-command">{INSTALL_COMMAND}</code>
        </pre>
        <p
          role="status"
          aria-live="polite"
          data-testid="landing-install-status"
          className="mt-2 min-h-5 text-ui-xs text-ink-soft"
        >
          {copy === 'copied' ? t('landing.install.copied') : null}
          {copy === 'failed' ? t('landing.install.copyFailed') : null}
        </p>
        <a
          href={`${REPO_BLOB}install.sh`}
          target="_blank"
          rel="noreferrer"
          className="focus-ring mt-1 inline-flex rounded-sm text-ui-xs text-ink-faint underline decoration-hairline underline-offset-4 hover:text-ink-soft"
        >
          {t('landing.install.read')}
        </a>

        <details className="mt-5 rounded-xl border border-hairline px-3 py-2.5">
          <summary className="focus-ring cursor-pointer text-ui-sm text-ink-soft">
            {t('landing.install.windows')}
          </summary>
          <pre
            tabIndex={0}
            className="mt-2 overflow-x-auto font-mono text-ui-xs break-words whitespace-pre-wrap text-foreground sm:whitespace-pre"
          >
            <code>{WINDOWS_COMMAND}</code>
          </pre>
          <p className="mt-1 text-ui-xs text-ink-faint">{t('landing.install.windowsNote')}</p>
        </details>

        <p className="mt-5 text-ui-sm leading-relaxed text-ink-soft">
          {t('landing.install.configure')}
        </p>
        <p className="mt-2 text-ui-sm leading-relaxed text-ink-soft">
          {t('landing.install.after')}
        </p>
      </div>
    </LandingSection>
  )
}
