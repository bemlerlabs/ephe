/**
 * Explicitly re-measure the currently mounted virtualizer rows.
 *
 * `virtualizer.measure()` only clears the size cache — existing DOM nodes are
 * NOT measured again afterwards: the `measureElement` ref callback is not
 * re-invoked for already-mounted nodes and the ResizeObserver stays silent
 * without an actual resize. Rows whose height changed while a stream was
 * scrolling (measurements gated by `shouldMeasureDuringScroll`) therefore
 * stay at the estimate and overlap their neighbours.
 *
 * Calling `measure(el)` for each mounted row lands the real heights
 * immediately. Returns the number of measured rows.
 */
export function remeasureRows(
  container: HTMLElement | null | undefined,
  rowSelector: string,
  measure: (el: HTMLElement) => void,
): number {
  if (!container) return 0
  const nodes = container.querySelectorAll<HTMLElement>(rowSelector)
  nodes.forEach((node) => measure(node))
  return nodes.length
}
