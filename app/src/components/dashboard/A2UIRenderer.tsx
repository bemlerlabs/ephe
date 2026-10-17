/**
 * Ephe — the A2UI renderer (M10, declarative generative UI).
 *
 * Renders an A2UI-v1.0-like JSON (an adjacency list) into React. The model can
 * return a fenced JSON block with `language: "a2ui"`; that block renders as a real
 * component surface instead of as raw code.
 *
 * A node names its children by id; a container puts them inside the element that
 * named them, so a Card owns what its `children` list. Components: Text, Heading,
 * Row, Column, List, Card, Button, Divider, Badge. Unknown ones fall back to text.
 *
 * A Button fires only through the `onAction` channel a caller hands in, and only
 * when the surface declares an `action` for it. Without either, it renders as a
 * plainly non-interactive chip instead of a control that looks clickable.
 */
import { Fragment, type ReactNode } from 'react'

/** What a Button hands back when it is wired to a real channel. */
export interface A2Action {
  name: string
  payload?: Record<string, unknown>
}

interface A2Node {
  id: string
  component?: string
  kind?: string
  text?: string
  value?: string
  label?: string
  items?: string[]
  children?: string[]
  /** The node's action contract: a name, or a name with a payload. */
  action?: string | { name?: string; payload?: Record<string, unknown> }
}
interface A2Surface {
  surfaceId?: string
  root?: string
  components?: A2Node[]
  // alternative adjacency form: a Map of id → Node
  [k: string]: unknown
}

function indexNodes(surface: A2Surface): Map<string, A2Node> {
  const map = new Map<string, A2Node>()
  const list = Array.isArray(surface.components) ? surface.components : null
  if (list) {
    for (const n of list) if (n && n.id) map.set(n.id, n)
    return map
  }
  // Map form: collect every value that carries an id field
  for (const v of Object.values(surface)) {
    if (v && typeof v === 'object') {
      const node = v as A2Node
      if (node.id) map.set(node.id, node)
    }
  }
  return map
}

function kindOf(node: A2Node): string {
  return (node.component || node.kind || 'text').toLowerCase()
}

/** The action a Button declares, or null when it declares none usable. */
function actionOf(node: A2Node): A2Action | null {
  const declared = node.action
  if (typeof declared === 'string') {
    const name = declared.trim()
    return name ? { name } : null
  }
  if (declared && typeof declared === 'object') {
    const name = typeof declared.name === 'string' ? declared.name.trim() : ''
    return name ? { name, payload: declared.payload } : null
  }
  return null
}

interface NodeProps {
  node: A2Node
  /** Depth in the surface graph; kept as the `data-a2-idx` a test or a reader sees. */
  index: number
  /** The already-rendered children of this node, or null when it has none. */
  kids: ReactNode
  onAction?: (action: A2Action) => void
}

/**
 * One component of the surface.
 *
 * Row, Column, Card and List are containers: `kids` goes inside the element.
 * A leaf kind (Text, Heading, Badge, Button, Divider) that carries children
 * renders them directly beneath itself — nesting a block element inside a
 * paragraph would be invalid HTML — so a branch is never dropped.
 */
function Node({ node, index, kids, onAction }: NodeProps) {
  switch (kindOf(node)) {
    case 'heading':
      return (
        <>
          <h4 className="text-ui-sm font-semibold text-foreground mt-2 mb-1">
            {node.text || node.value || ''}
          </h4>
          {kids}
        </>
      )
    case 'row':
      return <div className="flex flex-row gap-2 items-center my-1">{kids}</div>
    case 'column':
      return <div className="flex flex-col gap-1 my-1">{kids}</div>
    case 'list':
      return (
        <div className="my-1">
          <ul className="list-disc pl-5 space-y-0.5 text-ui-sm text-foreground/80">
            {(node.items || []).map((it, i) => (
              <li key={i}>{it}</li>
            ))}
          </ul>
          {kids}
        </div>
      )
    case 'card':
      return (
        <div className="rounded-lg border border-hairline bg-canvas px-3 py-2 my-1.5">
          {node.label && (
            <p className="text-ui-xs uppercase tracking-wide text-ink-faint mb-1">{node.label}</p>
          )}
          {node.text && <p className="text-ui-sm text-foreground/80">{node.text}</p>}
          {kids}
        </div>
      )
    case 'button': {
      const action = actionOf(node)
      const label = node.label || node.text || ''
      // A real button only where something can receive the action.
      if (action && onAction) {
        return (
          <>
            <button
              type="button"
              className="inline-flex items-center rounded px-1.5 py-0.5 text-ui-xs border border-hairline bg-surface text-foreground/80 hover:bg-canvas mr-1"
              data-a2ui-action={action.name}
              onClick={() => onAction(action)}
            >
              {label}
            </button>
            {kids}
          </>
        )
      }
      // No channel (or no declared action): the surface cannot fire this, so it
      // must not dress up as a control.
      return (
        <>
          <span
            className="inline-flex items-center rounded px-1.5 py-0.5 text-ui-xs border border-dashed border-hairline text-ink-faint mr-1"
            data-a2ui-inert="button"
            data-a2-idx={index}
          >
            {label}
          </span>
          {kids}
        </>
      )
    }
    case 'badge':
      return (
        <>
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-ui-xs bg-surface text-ink-faint mr-1">
            {node.text || node.label || ''}
          </span>
          {kids}
        </>
      )
    case 'divider':
      return (
        <>
          <hr className="border-hairline my-2" />
          {kids}
        </>
      )
    case 'text':
    default:
      return (
        <>
          <p className="text-ui-sm text-foreground/80 my-1" data-a2-idx={index}>
            {node.text || node.value || node.label || ''}
          </p>
          {kids}
        </>
      )
  }
}

/**
 * Parses an A2UI JSON string; returns null for invalid input, non-A2UI payloads,
 * and a surface that declares no node at all — an empty surface renders as an
 * empty box, which reads as a broken component instead of a code block.
 */
export function parseA2UI(raw: string): A2Surface | null {
  try {
    const obj = JSON.parse(raw) as A2Surface
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null
    return indexNodes(obj).size > 0 ? obj : null
  } catch {
    return null
  }
}

export default function A2UIRenderer({
  json,
  onAction,
}: {
  json: string
  /** The action channel. Without it a Button renders as non-interactive. */
  onAction?: (action: A2Action) => void
}) {
  const surface = parseA2UI(json)
  if (!surface) return null
  const nodes = indexNodes(surface)
  const rootId = surface.root || 'root'
  const order =
    surface.components && Array.isArray(surface.components)
      ? (surface.components as A2Node[]).map((n) => n.id)
      : [...nodes.keys()]
  // A surface is a graph, not a tree: an id reached twice renders once, which is
  // also what stops a node that names itself as its own child.
  const rendered = new Set<string>()
  const walk = (id: string, depth: number): ReactNode => {
    if (rendered.has(id)) return null
    const node = nodes.get(id)
    if (!node) return null
    rendered.add(id)
    const childEls = (node.children || []).map((cid, i) => (
      <Fragment key={`${cid}-${i}`}>{walk(cid, depth + 1)}</Fragment>
    ))
    return (
      <Node
        key={id}
        node={node}
        index={depth}
        kids={childEls.length > 0 ? childEls : null}
        onAction={onAction}
      />
    )
  }
  const roots = nodes.has(rootId) ? [rootId] : order
  return (
    <div className="a2ui my-1" data-testid="a2ui-root">
      {roots.map((id, i) => (
        <Fragment key={`${id}-${i}`}>{walk(id, 0)}</Fragment>
      ))}
    </div>
  )
}
