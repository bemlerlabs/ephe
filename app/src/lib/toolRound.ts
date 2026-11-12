import {
  Terminal,
  Pencil,
  FilePlus,
  FileText,
  Search,
  Globe,
  ListTodo,
  Package,
  Network,
  Wrench,
} from 'lucide-react'
import type { TFunction } from 'i18next'
import { classifyToolCall, isDiffLike, type ToolIconKind } from './toolCardModel'
import type { ToolCall } from '@/store/chatStore'

/**
 * UI-CHAT — the pure read of one tool call for the calm row.
 *
 * Kept out of the component file so the row anatomy (outcome word, failure
 * open rule) is testable without React, and so ToolCallDisplay only exports
 * components.
 */
export const ICONS: Record<ToolIconKind, typeof Terminal> = {
  terminal: Terminal,
  filePen: Pencil,
  filePlus: FilePlus,
  fileText: FileText,
  search: Search,
  globe: Globe,
  tasks: ListTodo,
  package: Package,
  subagent: Network,
  wrench: Wrench,
}

/** The one outcome word a row carries. Never a raw enum, never the tool name. */
export function toolOutcome(tool: ToolCall, t: TFunction): string {
  if (tool.status === 'pending') return t('chat.rowWorking')
  if (tool.status === 'waiting') return t('chat.toolWaiting')
  if (tool.status === 'denied' || tool.status === 'failed') return t('chat.rowFailed')
  const model = classifyToolCall(tool)
  if (tool.status === 'completed' && model.family === 'shell' && model.exit?.code !== 0) {
    return t('chat.rowFailed')
  }
  return t('chat.roundOk')
}

/** A failure the reader has to see at once; the row opens itself. */
export function isToolError(tool: ToolCall): boolean {
  if (tool.status === 'denied' || tool.status === 'failed') return true
  const model = classifyToolCall(tool)
  return (
    tool.status === 'completed' &&
    model.family === 'shell' &&
    model.exit !== null &&
    model.exit.code !== 0
  )
}

/** Failure, approval and a finished document open their body on mount. */
export function shouldAutoOpen(tool: ToolCall): boolean {
  if (tool.status === 'waiting' || tool.status === 'failed' || tool.status === 'denied') return true
  const model = classifyToolCall(tool)
  if (tool.status !== 'completed') return false
  if (isToolError(tool)) return true
  // A research run's cards are the reason the reader opens the row; the answer
  // text behind them is what the panel makes readable.
  if (tool.name === 'web_research') return true
  if (model.family === 'edit' && typeof tool.result === 'string' && isDiffLike(tool.result)) {
    return true
  }
  const content = tool.args?.['content']
  return model.family === 'write' && typeof content === 'string' && content.trim() !== ''
}
