// Agent Center and Agent Teams settings surfaces: list, editor, template and run.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { renderAgents } from './sections-agents'
import { renderTeams } from './sections-teams'
import type { SettingsModel } from './types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listAgents: vi.fn(),
    listAgentTools: vi.fn(),
    getModelProviders: vi.fn(),
    listAgentRuns: vi.fn(),
    createAgent: vi.fn(),
    updateAgent: vi.fn(),
    duplicateAgent: vi.fn(),
    setAgentArchived: vi.fn(),
    testAgent: vi.fn(),
    listTeams: vi.fn(),
    listTeamTemplates: vi.fn(),
    createTeam: vi.fn(),
    updateTeam: vi.fn(),
    setTeamArchived: vi.fn(),
    runTeam: vi.fn(),
    listTeamRuns: vi.fn(),
    getTeamRun: vi.fn(),
    cancelTeamRun: vi.fn(),
  }
})

import * as api from '@/lib/api'

const builtin = {
  id: 'ephe',
  name: 'Ephe',
  description: 'The default read-only helper.',
  avatar: { seed: 'Ephe', pattern: 'drop' },
  instructions: '',
  model: null,
  tools: ['read_file', 'web_search'],
  permissions: { approval: 'inherit', rules: [] },
  limits: { max_turns: 8, timeout: 180 },
  origin: 'ephe',
  enabled: true,
  archived: false,
  created_at: '',
  updated_at: '',
  read_only: true,
  etag: null,
}

const scout = {
  ...builtin,
  id: 'scout',
  name: 'Scout',
  description: 'Fast explorer',
  origin: 'local',
  enabled: true,
  read_only: false,
  etag: 'agent-1',
  instructions: 'Stay factual.',
  model: { provider: 'openai_compatible', model: 'gpt-x', tier: 'auto' },
}

const team = {
  id: 'research-team',
  name: 'Research team',
  description: 'Parallel sources',
  instructions: 'Stay sourced.',
  leader_id: 'scout',
  member_ids: ['ephe'],
  orchestration: 'parallel' as const,
  shared_context: { session: true, workspace: true, artifacts: false, memory: true },
  model_policy: 'inherit' as const,
  model: null,
  budget: { max_rounds: 4, wall_timeout: 300 },
  template: '',
  origin: 'local',
  archived: false,
  created_at: '',
  updated_at: '',
  read_only: false,
  etag: 'team-1',
}

function model(): SettingsModel {
  return {
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    setActiveTab: vi.fn(),
  } as unknown as SettingsModel
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listAgents).mockResolvedValue({
    agents: [builtin, scout],
    quarantined: {},
  } as never)
  vi.mocked(api.listAgentTools).mockResolvedValue({
    tools: [
      { name: 'read_file', families: ['read'] },
      { name: 'web_search', families: ['network'] },
    ],
  } as never)
  vi.mocked(api.getModelProviders).mockResolvedValue({
    active: { type: 'openai_compatible' },
    local_models: ['gpt-x'],
  } as never)
  vi.mocked(api.listAgentRuns).mockResolvedValue({ runs: [] } as never)
  vi.mocked(api.listTeams).mockResolvedValue({ teams: [team], quarantined: {} } as never)
  vi.mocked(api.listTeamTemplates).mockResolvedValue({
    templates: [{ key: 'research', name: 'Research team', description: 'd' }],
  } as never)
  vi.mocked(api.listTeamRuns).mockResolvedValue({ runs: [] } as never)
})

describe('Agent Center', () => {
  it('lists the default and local agents and opens the editor', async () => {
    render(renderAgents(model()))
    expect(await screen.findByTestId('agent-row-ephe')).toBeTruthy()
    expect(await screen.findByTestId('agent-row-scout')).toBeTruthy()
    fireEvent.click(screen.getByTestId('agent-edit-scout'))
    expect((screen.getByTestId('agent-name') as HTMLInputElement).value).toBe('Scout')
    expect((screen.getByTestId('agent-model') as HTMLInputElement).value).toBe('gpt-x')
  })

  it('turns a local agent off through its own endpoint', async () => {
    vi.mocked(api.updateAgent).mockResolvedValue({ ...scout, enabled: false } as never)
    render(renderAgents(model()))
    fireEvent.click(await screen.findByTestId('agent-toggle-scout'))
    await waitFor(() =>
      expect(api.updateAgent).toHaveBeenCalledWith('scout', { enabled: false }, 'agent-1'),
    )
  })

  it('duplicates a plugin agent instead of editing it in place', async () => {
    vi.mocked(api.duplicateAgent).mockResolvedValue({ ...scout, id: 'copy', name: 'Copy' } as never)
    render(renderAgents(model()))
    fireEvent.click(await screen.findByTestId('agent-duplicate-ephe'))
    await waitFor(() => expect(api.duplicateAgent).toHaveBeenCalledWith('ephe'))
  })

  it('saves an edited agent with its model pin', async () => {
    vi.mocked(api.updateAgent).mockResolvedValue({ ...scout, name: 'Scout 2' } as never)
    render(renderAgents(model()))
    fireEvent.click(await screen.findByTestId('agent-edit-scout'))
    fireEvent.change(screen.getByTestId('agent-name'), { target: { value: 'Scout 2' } })
    fireEvent.click(screen.getByTestId('agent-save'))
    await waitFor(() => expect(api.updateAgent).toHaveBeenCalled())
    const call = vi.mocked(api.updateAgent).mock.calls[0]
    expect(call).toBeTruthy()
    const payload = call![1]
    expect(payload.name).toBe('Scout 2')
    expect(payload.model).toEqual({ provider: 'openai_compatible', model: 'gpt-x', tier: 'auto' })
  })

  it('runs a test prompt and shows the report', async () => {
    vi.mocked(api.testAgent).mockResolvedValue({
      run_id: 'agent-test-1',
      agent_id: 'scout',
      agent_name: 'Scout',
      provider: 'openai_compatible',
      model: 'gpt-x',
      model_source: 'agent',
      status: 'ok',
      report: 'All clear.',
      tool_calls: [],
    } as never)
    render(renderAgents(model()))
    fireEvent.click(await screen.findByTestId('agent-edit-scout'))
    fireEvent.change(screen.getByTestId('agent-test-prompt'), {
      target: { value: 'Check the news' },
    })
    fireEvent.click(screen.getByTestId('agent-test-run'))
    expect(await screen.findByText('All clear.')).toBeTruthy()
  })
})

describe('Agent Teams', () => {
  it('lists teams and opens the editor', async () => {
    render(renderTeams(model()))
    expect(await screen.findByTestId('team-row-research-team')).toBeTruthy()
    fireEvent.click(screen.getByTestId('team-edit-research-team'))
    expect((screen.getByTestId('team-name') as HTMLInputElement).value).toBe('Research team')
  })

  it('creates a team from a template', async () => {
    vi.mocked(api.createTeam).mockResolvedValue({ ...team, id: 'new-team' } as never)
    render(renderTeams(model()))
    fireEvent.click(await screen.findByTestId('team-create'))
    fireEvent.click(screen.getByTestId('team-template-research'))
    await waitFor(() =>
      expect(api.createTeam).toHaveBeenCalledWith({
        template: 'research',
        name: 'settings.teamTemplateResearchName',
        description: 'settings.teamTemplateResearchDesc',
      }),
    )
  })

  it('runs a team and shows the leader report', async () => {
    vi.mocked(api.runTeam).mockResolvedValue({
      run_id: 'team-abcd1234',
      team_id: 'research-team',
      status: 'ok',
      report: 'Team answer.',
      members: [
        {
          agent_id: 'ephe',
          name: 'Ephe',
          model: '',
          model_source: 'global',
          status: 'ok',
          duration_ms: 3,
          report: 'm',
          tool_calls: 0,
          role: 'member',
        },
        {
          agent_id: 'scout',
          name: 'Scout',
          model: '',
          model_source: 'global',
          status: 'ok',
          duration_ms: 2,
          report: 's',
          tool_calls: 0,
          role: 'leader',
        },
      ],
      budget_hit: false,
      duration_ms: 9,
    } as never)
    render(renderTeams(model()))
    fireEvent.click(await screen.findByTestId('team-edit-research-team'))
    fireEvent.change(screen.getByTestId('team-run-task'), {
      target: { value: 'What changed?' },
    })
    fireEvent.click(screen.getByTestId('team-run-start'))
    expect(await screen.findByText('Team answer.')).toBeTruthy()
    await waitFor(() => expect(api.runTeam).toHaveBeenCalled())
    expect(vi.mocked(api.runTeam).mock.calls[0]?.[1]).toBe('What changed?')
  })
})
