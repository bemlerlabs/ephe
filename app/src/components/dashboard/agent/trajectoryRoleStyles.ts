/**
 * P6/A1: trajectory roles → the text colour utility.
 *
 * The colours live as primitive tokens in the @theme block of globals.css
 * (--color-trajectory-*), the dark steps in the .dark block. This map is the ONE
 * source for role assignment inside the trajectory pane.
 */

/** Role type string (agent event) → Tailwind text colour class.
 *  The backend stores the event types UPPERCASE (core/trajectory.py:
 *  `etype.upper()`), so the lookup normalises to lowercase. */
const TRAJECTORY_ROLE_CLASSES: Record<string, string> = {
  thinking_start: 'text-trajectory-reasoning',
  thinking_chunk: 'text-trajectory-reasoning',
  thinking: 'text-trajectory-reasoning',
  reasoning: 'text-trajectory-reasoning',
  reflect: 'text-trajectory-reasoning',
  revision: 'text-trajectory-reasoning',
  message: 'text-trajectory-assistant',
  assistant: 'text-trajectory-assistant',
  activity: 'text-trajectory-assistant',
  user: 'text-trajectory-user',
  tool_call: 'text-trajectory-tool-call',
  tool_start: 'text-trajectory-tool-call',
  tool_done: 'text-trajectory-tool-call',
  tool_result: 'text-trajectory-tool-result',
  file_result: 'text-trajectory-tool-result',
  artifact: 'text-trajectory-tool-result',
  usage: 'text-mist-dim',
}

/** Fallback for unknown types: a subdued UI text-size class. */
const TRAJECTORY_FALLBACK_CLASS = 'text-ui-sm'

export function trajectoryRoleTextClass(type: string): string {
  return TRAJECTORY_ROLE_CLASSES[type.toLowerCase()] ?? TRAJECTORY_FALLBACK_CLASS
}

/** N4′: the same colour series as a 2px left border mark on the step row —
 *  it shows the step type even when the details are collapsed. */
const TRAJECTORY_ROLE_MARKER_CLASSES: Record<string, string> = {
  thinking_start: 'border-l-trajectory-reasoning',
  thinking_chunk: 'border-l-trajectory-reasoning',
  thinking: 'border-l-trajectory-reasoning',
  reasoning: 'border-l-trajectory-reasoning',
  reflect: 'border-l-trajectory-reasoning',
  revision: 'border-l-trajectory-reasoning',
  message: 'border-l-trajectory-assistant',
  assistant: 'border-l-trajectory-assistant',
  activity: 'border-l-trajectory-assistant',
  user: 'border-l-trajectory-user',
  tool_call: 'border-l-trajectory-tool-call',
  tool_start: 'border-l-trajectory-tool-call',
  tool_done: 'border-l-trajectory-tool-call',
  tool_result: 'border-l-trajectory-tool-result',
  file_result: 'border-l-trajectory-tool-result',
  artifact: 'border-l-trajectory-tool-result',
  usage: 'border-l-mist-dim',
}
const TRAJECTORY_MARKER_FALLBACK = 'border-l-transparent'

export function trajectoryRoleMarkerClass(type: string): string {
  return TRAJECTORY_ROLE_MARKER_CLASSES[type.toLowerCase()] ?? TRAJECTORY_MARKER_FALLBACK
}
