/**
 * A click on the cast picture, mapped into the page's own viewport.
 *
 * The picture is drawn with object-contain, so the element can be wider or taller
 * than the page. A click in that spare margin is not a point on the page.
 */

export interface PointerBox {
  left: number
  top: number
  width: number
  height: number
}

export function pointerToViewport(
  frame: { viewportWidth: number; viewportHeight: number },
  box: PointerBox,
  clientX: number,
  clientY: number,
): { x: number; y: number } | null {
  const viewportWidth = frame.viewportWidth
  const viewportHeight = frame.viewportHeight
  if (viewportWidth <= 0 || viewportHeight <= 0 || box.width <= 0 || box.height <= 0) return null
  const scale = Math.min(box.width / viewportWidth, box.height / viewportHeight)
  const drawnWidth = viewportWidth * scale
  const drawnHeight = viewportHeight * scale
  const localX = clientX - box.left - (box.width - drawnWidth) / 2
  const localY = clientY - box.top - (box.height - drawnHeight) / 2
  if (localX < 0 || localY < 0 || localX > drawnWidth || localY > drawnHeight) return null
  return {
    x: Math.min(viewportWidth - 1, Math.max(0, Math.floor((localX / drawnWidth) * viewportWidth))),
    y: Math.min(
      viewportHeight - 1,
      Math.max(0, Math.floor((localY / drawnHeight) * viewportHeight)),
    ),
  }
}
