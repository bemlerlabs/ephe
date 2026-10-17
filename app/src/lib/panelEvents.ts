/**
 * Ephe — panel event constants (single source).
 *
 * Chat elements (tool cards, artifact chips …) and the agent panel host
 * communicate through these named window events. They deliberately live in a
 * lightweight module so that card renderers do not have to pull in the heavy
 * AgentPanel import for them.
 */
export const PREVIEW_OPEN_EVENT = 'ephe:preview-open'
export const PANEL_STATE_EVENT = 'ephe:panel-state'
/** [F9] Query map: jump to a user message. `detail.messageId` = ChatMessage.id. */
export const QUERY_JUMP_EVENT = 'ephe:query-jump'
