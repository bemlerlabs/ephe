'use client'

import {
  Bot,
  Database,
  Folder,
  GitBranch,
  Globe,
  Globe2,
  History,
  MessagesSquare,
  ScrollText,
  TerminalSquare,
} from 'lucide-react'
import { Tab } from './primitives'

export function TabIcon({ tab }: { tab: Tab }) {
  const cls = 'h-3.5 w-3.5'
  switch (tab) {
    case 'preview':
      return <Globe className={cls} />
    case 'terminal':
      return <TerminalSquare className={cls} />
    case 'git':
      return <GitBranch className={cls} />
    case 'files':
      return <Folder className={cls} />
    case 'audit':
      return <ScrollText className={cls} />
    case 'trajectory':
      return <History className={cls} />
    case 'subagents':
      return <Bot className={cls} />
    case 'memory':
      return <Database className={cls} />
    case 'browser':
      return <Globe2 className={cls} />
    case 'side':
      return <MessagesSquare className={cls} />
  }
}
