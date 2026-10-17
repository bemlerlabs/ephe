import { FileText, X } from 'lucide-react'
import type { ChatAttachment } from '@/lib/attachments'

export type { ChatAttachment as Attachment }

interface AttachmentPreviewProps {
  attachments: ChatAttachment[]
  onRemove: (index: number) => void
}

/**
 * G3: Attached files as chips — images with a thumbnail,
 * text/binary with an icon. Rendered below the input.
 */
export default function AttachmentPreview({ attachments, onRemove }: AttachmentPreviewProps) {
  if (attachments.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {attachments.map((att, i) => (
        <div
          key={`${att.path}-${i}`}
          className="flex items-center gap-1.5 bg-surface border border-hairline rounded-lg px-2 py-1 text-ui-xs text-foreground/70 max-w-[240px]"
        >
          {att.kind === 'image' ? (
            <img src={att.dataUrl} alt="" className="h-5 w-5 rounded object-cover flex-shrink-0" />
          ) : (
            <FileText className="h-3.5 w-3.5 text-brand flex-shrink-0" />
          )}
          <span className="truncate">
            {att.name}
            {att.kind === 'text' && att.truncated ? ' …' : ''}
          </span>
          <button
            onClick={() => onRemove(i)}
            className="text-ink-faint hover:text-status-danger transition-colors ml-1 flex-shrink-0"
            aria-label="Attachment entfernen"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  )
}
