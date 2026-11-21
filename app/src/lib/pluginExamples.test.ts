import { describe, expect, it } from 'vitest'

import { examplePromptFor } from './pluginExamples'

describe('plugin examples', () => {
  it('keeps the former duplicate pair on different examples', () => {
    expect(examplePromptFor('private-research-notebook')).not.toBe(
      examplePromptFor('web-research'),
    )
    expect(examplePromptFor('documents')).not.toBe(examplePromptFor('local-document-factory'))
  })

  it('names an unknown plugin instead of inventing a capability', () => {
    expect(examplePromptFor('mystery', 'Mystery Box')).toContain('Mystery Box')
  })
})
