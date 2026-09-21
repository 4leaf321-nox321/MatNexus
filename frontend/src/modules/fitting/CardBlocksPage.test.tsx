/**
 * 카드 항목란 화면 (ADR 0033).
 *
 * 여기서 지키는 것은 「만들 수 있다」 가 아니라 **무엇을 못 하는지가 보이는가**다:
 * 내장 항목란은 고칠 수 없고, 켜 뒀는데 안 얹힌 것은 눈에 띄어야 하고, 키는 한 번
 * 만들면 못 바꾼다. 셋 다 화면이 말하지 않으면 사람은 저장 단계에서야 안다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CardBlocksPage from '@/modules/fitting/CardBlocksPage'

const blockDefinitions = vi.fn()
const blocks = vi.fn()
const createBlockDefinition = vi.fn()
const updateBlockDefinition = vi.fn()

vi.mock('@/modules/fitting/api', () => ({
  fittingApi: {
    blockDefinitions: () => blockDefinitions(),
    blocks: () => blocks(),
    createBlockDefinition: (...args: unknown[]) => createBlockDefinition(...args),
    updateBlockDefinition: (...args: unknown[]) => updateBlockDefinition(...args),
    removeBlockDefinition: vi.fn(),
  },
}))

vi.mock('@/modules/tests/api', () => ({
  testsApi: { types: () => Promise.resolve([{ key: 'tensile', label: '인장' }]) },
}))

let isAdmin = true

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: isAdmin } }),
}))

const MADE = {
  id: 'b1',
  key: 'anisotropy',
  label: '이방성',
  help: '세 방향 인장에서 나오는 r값들.',
  produces: [{ key: 'r_bar', label: '평균 이방성', si_unit: '1' }],
  rows: [],
  sort_order: 200,
  kind_priority: null,
  curve_x: null,
  curve_y: null,
  from_tests: ['tensile'],
  measured: true,
  version: 1,
  enabled: true,
  installed: true,
  card_count: 0,
  created_at: '2026-09-21T00:00:00Z',
  updated_at: '2026-09-21T00:00:00Z',
}

beforeEach(() => {
  isAdmin = true
  blockDefinitions.mockReset()
  blockDefinitions.mockResolvedValue([MADE])
  blocks.mockReset()
  blocks.mockResolvedValue([
    { key: 'elastic', label: '탄성', help: '', produces: [], rows: [], in_deck: true },
    { key: 'anisotropy', label: '이방성', help: '', produces: [], rows: [], in_deck: false },
  ])
  createBlockDefinition.mockReset()
  createBlockDefinition.mockResolvedValue(MADE)
  updateBlockDefinition.mockReset()
  updateBlockDefinition.mockResolvedValue({ ...MADE, enabled: false })
})

describe('카드 항목란', () => {
  it('만든 것과 내장을 갈라 보여 준다', async () => {
    render(<CardBlocksPage />)

    // 만든 것은 표에 — 고칠 수 있다.
    expect(await screen.findByRole('button', { name: '이방성 고치기' })).toBeInTheDocument()
    // 내장은 이름만 — **같은 키를 쓰려다 저장에서 막히는 것보다 먼저 보는 편이 낫다.**
    expect(await screen.findByText('탄성')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '탄성 고치기' })).not.toBeInTheDocument()
  })

  it('켜 뒀는데 못 얹혔으면 눈에 띈다', async () => {
    // 선언에 탈이 난 상태다 — 조용히 「켜짐」 으로 두면 왜 안 보이는지 알 길이 없다.
    blockDefinitions.mockResolvedValue([{ ...MADE, installed: false }])
    render(<CardBlocksPage />)
    expect(await screen.findByText('못 얹음')).toBeInTheDocument()
  })

  it('고칠 때 키는 잠긴다 — 카드가 그 키로 값을 들고 있다', async () => {
    const user = userEvent.setup()
    render(<CardBlocksPage />)
    await user.click(await screen.findByRole('button', { name: '이방성 고치기' }))

    expect(await screen.findByLabelText('키')).toBeDisabled()
    expect(screen.getByText(/카드가 이 키로 값을 들고 있어/)).toBeInTheDocument()
  })

  it('새로 만들면 키와 값 한 줄을 보낸다', async () => {
    const user = userEvent.setup()
    render(<CardBlocksPage />)
    await user.click(await screen.findByRole('button', { name: /항목란 만들기/ }))

    await user.type(await screen.findByLabelText('키'), 'formability')
    await user.type(screen.getByLabelText('이름'), '성형성')
    await user.type(screen.getByLabelText('담는 값 1 키'), 'fld_0')
    await user.type(screen.getByLabelText('담는 값 1 이름'), 'FLD0')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(createBlockDefinition).toHaveBeenCalled())
    const sent = createBlockDefinition.mock.calls[0][0] as Record<string, unknown>
    expect(sent.key).toBe('formability')
    expect(sent.produces).toEqual([{ key: 'fld_0', label: 'FLD0', si_unit: '1' }])
  })

  it('시스템 관리자가 아니면 고치는 길이 없다', async () => {
    isAdmin = false
    render(<CardBlocksPage />)
    expect(await screen.findByText('이방성')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /항목란 만들기/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '이방성 고치기' })).not.toBeInTheDocument()
  })
})
