import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import ChatInput from '@/components/dashboard/ChatInput'

// Walkthrough finding: the /help row rendered under the SKILLS heading. A help
// skill declares trigger "/help", exactly the built-in command's token, and the
// composer split the suggestions by the skill list — so the built-in row was
// filed as a skill.

vi.mock('@/lib/api', () => ({
  getModelProviders: () => Promise.reject(new Error('offline')),
  getSetupStatus: () => Promise.reject(new Error('offline')),
  getSettings: () => Promise.resolve({ workspace_dir: '/tmp/ws' }),
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      entries: [],
    }),
  listSkills: () =>
    Promise.resolve({
      skills: [
        { name: 'help', trigger: '/help', description: 'Shows an overview of all features' },
        { name: 'factory', trigger: '/factory', description: 'Builds runnable projects' },
      ],
    }),
}))

const FOLLOWING = Node.DOCUMENT_POSITION_FOLLOWING
const follows = (before: Element, after: Element) =>
  Boolean(before.compareDocumentPosition(after) & FOLLOWING)

describe('the slash menu files built-in commands as commands', () => {
  it('a skill trigger that collides with a built-in leaves the built-in under COMMANDS', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: '/' } })
    await screen.findByTestId('slash-group-skills')

    const commands = screen.getByTestId('slash-group-commands')
    const skills = screen.getByTestId('slash-group-skills')
    const helpRow = document.getElementById('slash-opt-help')
    expect(helpRow).toBeTruthy()
    expect(follows(commands, helpRow!)).toBe(true)
    expect(follows(helpRow!, skills)).toBe(true)
  })

  it('the skill behind the collision still reaches the menu under SKILLS', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: '/' } })
    await screen.findByTestId('slash-group-skills')

    const skills = screen.getByTestId('slash-group-skills')
    const factoryRow = document.getElementById('slash-opt-factory')
    expect(factoryRow).toBeTruthy()
    expect(follows(skills, factoryRow!)).toBe(true)
  })
})
