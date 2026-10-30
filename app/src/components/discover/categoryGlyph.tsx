/** One glyph per subject. A shelf is read from its marks before its words, so
 *  every entry carries the mark of what it is for; the kind is the fallback. */
import type { LucideIcon } from 'lucide-react'
import {
  Box,
  Brain,
  Cloud,
  Code2,
  Database,
  FlaskConical,
  FolderOpen,
  Globe,
  Image as ImageIcon,
  ListChecks,
  MessagesSquare,
  Package,
  Plug,
  Puzzle,
  ShieldCheck,
  Sparkles,
  Wrench,
} from 'lucide-react'
import type { DiscoverKind } from './discoverModel'

const BY_CATEGORY: Record<string, LucideIcon> = {
  skills: Sparkles,
  code: Code2,
  web: Globe,
  memory: Brain,
  files: FolderOpen,
  communication: MessagesSquare,
  productivity: ListChecks,
  database: Database,
  cloud: Cloud,
  security: ShieldCheck,
  media: ImageIcon,
  utility: Wrench,
  testing: FlaskConical,
  sandbox: Box,
  other: Package,
}

const BY_KIND: Record<DiscoverKind, LucideIcon> = {
  skill: Sparkles,
  connector: Plug,
  plugin: Puzzle,
}

export function glyphFor(category: string | undefined, kind: DiscoverKind): LucideIcon {
  return (category ? BY_CATEGORY[category] : undefined) ?? BY_KIND[kind]
}

export function CategoryGlyph({
  category,
  kind,
  className = 'h-4 w-4',
}: {
  category?: string
  kind: DiscoverKind
  className?: string
}) {
  const Glyph = glyphFor(category, kind)
  return <Glyph aria-hidden="true" strokeWidth={1.5} className={className} />
}
