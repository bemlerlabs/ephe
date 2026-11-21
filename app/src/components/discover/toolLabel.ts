/** Tool ids are written for the engine; the bench is read by a person. The
 *  known names are spelled the way the product speaks about them, everything
 *  else is only unfolded, never guessed. */
const KNOWN: Record<string, string> = {
  tool_call: 'Tool call',
  tool_search: 'Tool search',
  web_search: 'Web search',
  web_fetch: 'Web fetch',
  read_file: 'Read file',
  write_file: 'Write file',
  list_directory: 'List folder',
  search_files: 'Search files',
  browser_evaluate: 'Browser evaluate',
  browser_snapshot: 'Browser snapshot',
  shell_exec: 'Shell command',
}

export function toolLabel(tool: string): string {
  const known = KNOWN[tool]
  if (known) return known
  const tail = tool.includes('__') ? (tool.split('__').pop() ?? tool) : tool
  const words = tail
    .replace(/[._-]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
  if (!words.length) return tool
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
}
