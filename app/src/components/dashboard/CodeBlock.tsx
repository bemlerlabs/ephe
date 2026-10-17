import { useState, useCallback, useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy } from 'lucide-react'
import { highlightFence } from '@/lib/syntaxHighlighter'

/** Extracts the raw text out of React children (for the copy button) */
function toText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(toText).join('')
  if (typeof node === 'object' && 'props' in node) {
    const p = node.props as { children?: ReactNode }
    return toText(p.children)
  }
  return ''
}

interface CodeBlockProps {
  children?: ReactNode
  /** F-01: code rendered directly (no Markdown AST) — e.g. detector artifacts */
  code?: string
  language?: string
  /** On a finalised message: colour the fence once the highlighter has landed.
   *  Off while streaming — the plain text is readable on the first render and
   *  the pipeline does not hold a chunk back for a grammar. */
  highlight?: boolean
}

/** Fenced code block: header with language + copy, below it the child element's
 *  <pre>...</pre>. The chat path hands this a `<code class="language-x">`, the
 *  preview surfaces one the eager highlighter has already given hljs classes. */
export default function CodeBlock({ children, code, language, highlight }: CodeBlockProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [tokens, setTokens] = useState<string | null>(null)

  // Language from the inner <code> element's className (language-xxx)
  let lang: string | undefined
  let codeElement: ReactNode | null = null
  const child = Array.isArray(children) ? children[0] : children
  if (child != null && typeof child === 'object' && 'props' in child) {
    const props = child.props as { className?: string; children?: ReactNode }
    lang = props.className ? /language-(\S+)/.exec(props.className)?.[1] : undefined
    codeElement = child
  }
  if (code != null) lang = language

  const source = code ?? toText(children)

  // The token spans replace the plain text on the same node the copy button
  // reads its text from, so a copy during or after the swap yields the code.
  useEffect(() => {
    if (!highlight) {
      setTokens(null)
      return
    }
    let cancelled = false
    void highlightFence(source, (lang ?? 'text').toLowerCase()).then((html) => {
      if (!cancelled) setTokens(html)
    })
    return () => {
      cancelled = true
    }
  }, [highlight, source, lang])

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(source).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [source])

  const fence =
    tokens != null ? (
      // Safe by construction: `tokens` is the highlighter's own HTML for the
      // fence, produced from the code text with every token escaped, and it
      // carries nothing but <span style="color:#..."> and <br>.
      <code
        className={`syntax-tokens language-${lang ?? 'text'}`}
        dangerouslySetInnerHTML={{ __html: tokens }}
      />
    ) : (
      (codeElement ??
      (code != null ? <code className={`hljs language-${lang ?? 'text'}`}>{code}</code> : null))
    )

  return (
    <div className="relative group/code my-3">
      <div className="flex items-center justify-between bg-canvas border border-hairline rounded-t-lg px-3 py-1.5">
        <span className="text-ui-xs text-ink-soft font-mono uppercase tracking-wide">
          {lang || 'text'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-ui-xs text-ink-faint hover:text-brand transition-colors"
          aria-label={copied ? t('codeBlock.copied') : t('codeBlock.copy')}
        >
          {copied ? (
            <Check className="h-3 w-3 text-status-success" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
          {copied ? t('codeBlock.copied') : t('codeBlock.copy')}
        </button>
      </div>
      {fence ? (
        <pre className="bg-canvas border border-t-0 border-hairline rounded-b-lg overflow-x-auto">
          {fence}
        </pre>
      ) : null}
    </div>
  )
}
