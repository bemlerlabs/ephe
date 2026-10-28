import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@/i18n'

const api = vi.hoisted(() => ({ adoptArtifact: vi.fn() }))
const flow = vi.hoisted(() => ({ adoptWithTarget: vi.fn() }))

vi.mock('@/lib/api', () => ({ adoptArtifact: api.adoptArtifact }))
vi.mock('./adoptFlow', () => ({ adoptWithTarget: flow.adoptWithTarget }))

import { RailAdoptAction } from './RailAdoptAction'

beforeEach(() => {
  api.adoptArtifact.mockReset()
  flow.adoptWithTarget.mockReset()
})

describe('the rail adopt action', () => {
  it('adopts through the shared gesture and marks the row', async () => {
    flow.adoptWithTarget.mockResolvedValue({ adopted_path: '/tmp/a.pdf' })
    render(<RailAdoptAction id="art-1" name="a.pdf" />)
    fireEvent.click(screen.getByTestId('artifact-row-adopt-art-1'))
    await waitFor(() => {
      expect(screen.getByTestId('artifact-row-adopted-art-1')).toBeTruthy()
    })
    expect(flow.adoptWithTarget).toHaveBeenCalledWith('art-1', 'a.pdf', 'Adopt')
  })

  it('asks for a path when the server has no remembered target', async () => {
    flow.adoptWithTarget.mockRejectedValue(new Error('destination is required'))
    render(<RailAdoptAction id="art-2" name="b.pdf" />)
    fireEvent.click(screen.getByTestId('artifact-row-adopt-art-2'))
    const input = await screen.findByTestId('artifact-row-adopt-path-art-2')
    expect(input).toBeTruthy()
    fireEvent.change(input.querySelector('input')!, { target: { value: '/tmp/x' } })
    api.adoptArtifact.mockResolvedValue({ adopted_path: '/tmp/x/b.pdf' })
    fireEvent.click(screen.getByTestId('artifact-row-adopt-send-art-2'))
    await waitFor(() => {
      expect(screen.getByTestId('artifact-row-adopted-art-2')).toBeTruthy()
    })
    expect(api.adoptArtifact).toHaveBeenCalledWith('art-2', '/tmp/x')
  })

  it('says the adoption failed instead of pretending otherwise', async () => {
    flow.adoptWithTarget.mockRejectedValue(new Error('outside the allowed roots'))
    render(<RailAdoptAction id="art-3" name="c.pdf" />)
    fireEvent.click(screen.getByTestId('artifact-row-adopt-art-3'))
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toBeTruthy()
    })
  })
})
