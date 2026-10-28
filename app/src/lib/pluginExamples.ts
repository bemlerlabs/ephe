/**
 * One concrete example per first-party plugin, used by the "try it" buttons in the
 * marketplace and the installed list. The catalog index carries no prompt text, so
 * the examples live with the product's own copy; an unknown plugin gets a prompt
 * that names the plugin instead of inventing a capability for it.
 */
const EXAMPLES: Record<string, string> = {
  'browser-use':
    'Open example.com in the browser, take a screenshot, and tell me what is on the page.',
  'code-shell': "Run `python3 -c 'print(2**10)'` in the shell and show me the output.",
  documents: 'List the documents in my workspace and summarise the most recent one.',
  guide: 'Walk me through the first steps of this app and point me to the settings I need.',
  'image-studio': 'Create a simple 512×512 image of a calm forest at dawn and save it locally.',
  'local-document-factory': 'Turn these notes into a clean Markdown document and save it locally.',
  'mcp-connector': 'List the MCP servers you can reach and what tools each one exposes.',
  memory: 'Remember that I prefer short answers before details, and confirm what you stored.',
  'plugin-creator': 'Create a minimal plugin scaffold named hello-world with one command.',
  presentations: 'Draft a three-slide outline for a project update and save it as a deck.',
  'private-research-notebook':
    'Research this topic from my local notes only and write a private brief.',
  'skill-creator': 'Create a skill that reviews a diff for security issues, triggered by /security-review.',
  spreadsheets: 'Build a small spreadsheet with three columns and one formula, then save it.',
  vision: 'Analyse the image I attach and describe what is in it.',
  voice: 'Transcribe this short audio clip and return the text.',
  'web-research': 'Research the current state of WebAssembly in browsers and cite three sources.',
}

export function examplePromptFor(pluginId: string, displayName?: string): string {
  const known = EXAMPLES[pluginId]
  if (known) return known
  return `Show me what ${displayName || pluginId} can do, with one concrete example.`
}
