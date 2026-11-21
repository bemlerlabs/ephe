/**
 * N7 — the OCR text travels with the message it belongs to.
 *
 * Vision runs before the send; the text it read is appended to the outgoing
 * turn in a shape every engine reads as data, with the file name beside it so
 * the model can tell two screenshots apart. Attachments without text leave the
 * message untouched.
 */
import type { ChatAttachment } from './attachments'

export function annotateWithOcr(message: string, attachments: ChatAttachment[] | undefined): string {
  const blocks = (attachments ?? [])
    .filter((attachment) => attachment.ocrText)
    .map((attachment) => `[Text from image ${attachment.name}:\n${attachment.ocrText}]`)
  if (blocks.length === 0) return message
  return `${message}\n\n${blocks.join('\n\n')}`
}
