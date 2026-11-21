/**
 * Leaf boxes inside one row, clipped by every scrollable ancestor.
 *
 * Two leaves collide when their visible rectangles overlap by more than 4 px on both axes and
 * neither contains the other. Taking the clip rectangle of both parents is what still leaves a
 * visible overlap behind: a scroll strip may clip a box, painting one control over another may
 * not. `id` names an offender by its test id, its accessible label, or its first words.
 */
export function collisionProbe(sel: string) {
  const root = document.querySelector(sel)
  if (!root) return { missing: true, hits: [] as string[] }
  const vis = (el: Element) => {
    const b = el.getBoundingClientRect()
    let r = { x: b.x, y: b.y, right: b.right, bottom: b.bottom }
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const st = getComputedStyle(p)
      if (/hidden|auto|scroll|clip/.test(st.overflowX + st.overflowY)) {
        const pb = p.getBoundingClientRect()
        r = {
          x: Math.max(r.x, pb.x),
          y: Math.max(r.y, pb.y),
          right: Math.min(r.right, pb.right),
          bottom: Math.min(r.bottom, pb.bottom),
        }
      }
    }
    return r
  }
  const leaves = [...root.querySelectorAll('*')]
    .filter((el) => {
      const tag = el.tagName
      if (!['BUTTON', 'SPAN', 'P', 'H1', 'A'].includes(tag)) return false
      if (tag === 'BUTTON' || tag === 'A') {
        if (el.querySelector('button, a')) return false
      } else if (el.querySelector('button, span, p, h1, a, svg')) return false
      const b = el.getBoundingClientRect()
      return b.width > 2 && b.height > 2
    })
    .map((el) => {
      const r = vis(el)
      return {
        id:
          el.getAttribute('data-testid') ||
          el.getAttribute('aria-label') ||
          el.textContent?.trim().slice(0, 16) ||
          el.tagName,
        ...r,
      }
    })
  const hits: string[] = []
  for (let i = 0; i < leaves.length; i++)
    for (let j = i + 1; j < leaves.length; j++) {
      const a = leaves[i],
        b = leaves[j]
      const inside =
        (a.x <= b.x && a.right >= b.right && a.y <= b.y && a.bottom >= b.bottom) ||
        (b.x <= a.x && b.right >= a.right && b.y <= a.y && b.bottom >= a.bottom)
      if (inside) continue
      const ox = Math.min(a.right, b.right) - Math.max(a.x, b.x)
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y)
      if (ox > 4 && oy > 4) hits.push(`${a.id} ⨯ ${b.id} (${Math.round(ox)}x${Math.round(oy)}px)`)
    }
  return { missing: false, hits }
}
