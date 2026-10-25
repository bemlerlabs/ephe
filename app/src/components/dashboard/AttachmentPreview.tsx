import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertCircle, FileText, Loader2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatBytes, type ChatAttachment } from '@/lib/attachments'
import './AttachmentPreview.css'

export type { ChatAttachment as Attachment }

interface AttachmentPreviewProps {
  attachments: ChatAttachment[]
  onRemove: (index: number) => void
}

/**
 * G3: attached files as cards below the input — an image shows a thumbnail that
 * opens a lightbox, text and binary files show their name and size. The card
 * reports a file it is still reading and one it could not read; removal names
 * the file it removes instead of saying "remove".
 */
export default function AttachmentPreview({ attachments, onRemove }: AttachmentPreviewProps) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState<{ src: string; name: string } | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!preview) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreview(null)
    }
    document.addEventListener('keydown', onKey)
    closeRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [preview])

  useEffect(() => {
    if (preview) return
    const target = returnFocus.current
    if (target) {
      target.focus()
      returnFocus.current = null
    }
  }, [preview])

  if (attachments.length === 0) return null
  return (
    <>
      <ul className="attachment-strip" aria-label={t('attachment.list')}>
        {attachments.map((att, index) => {
          const state = att.status ?? 'ready'
          const size = formatBytes(att.size)
          return (
            <li
              key={`${att.path}-${index}`}
              className="attachment-card"
              data-kind={att.kind}
              data-state={state}
            >
              {att.kind === 'image' && state === 'ready' ? (
                <button
                  type="button"
                  className="attachment-thumb"
                  data-testid="attachment-thumb"
                  aria-label={t('attachment.preview', { name: att.name })}
                  onClick={(event) => {
                    returnFocus.current = event.currentTarget
                    setPreview({ src: att.dataUrl, name: att.name })
                  }}
                >
                  <img src={att.dataUrl} alt="" />
                </button>
              ) : state === 'loading' ? (
                <Loader2 className="attachment-icon animate-spin" aria-hidden="true" />
              ) : state === 'error' ? (
                <AlertCircle
                  className="attachment-icon attachment-icon-error"
                  aria-hidden="true"
                />
              ) : (
                <FileText className="attachment-icon" aria-hidden="true" />
              )}
              <span className="attachment-meta">
                <span className="attachment-name" title={att.name}>
                  {att.name}
                </span>
                {state === 'error' ? (
                  <span className="attachment-state-error">
                    {t('attachment.readFailed', { name: att.name })}
                  </span>
                ) : (
                  <span className="attachment-size">
                    {state === 'loading'
                      ? t('attachment.loading', { name: att.name })
                      : size
                        ? t('attachment.size', { size })
                        : ''}
                  </span>
                )}
              </span>
              <button
                type="button"
                className="attachment-remove"
                data-testid="attachment-remove"
                onClick={() => onRemove(index)}
                aria-label={t('attachment.remove', { name: att.name })}
              >
                <X aria-hidden="true" />
              </button>
            </li>
          )
        })}
      </ul>
      {preview &&
        createPortal(
          <div
            className="attachment-lightbox"
            data-testid="attachment-lightbox"
            role="dialog"
            aria-modal="true"
            aria-label={t('attachment.preview', { name: preview.name })}
            onClick={() => setPreview(null)}
          >
            <button
              ref={closeRef}
              type="button"
              className="attachment-lightbox-close"
              onClick={() => setPreview(null)}
              aria-label={t('attachment.close')}
            >
              <X aria-hidden="true" />
            </button>
            <img
              src={preview.src}
              alt={preview.name}
              onClick={(event) => event.stopPropagation()}
            />
          </div>,
          document.body,
        )}
    </>
  )
}
