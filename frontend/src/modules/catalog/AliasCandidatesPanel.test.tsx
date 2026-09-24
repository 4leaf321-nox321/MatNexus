/**
 * 별칭 후보 판 — 물성을 **이름으로 골라** 받아들이고, 무시는 목록에서 내린다.
 * 키를 손으로 치게 하지 않는다 — 오타 하나로 별칭이 허공을 가리킨다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AliasCandidatesPanel } from '@/modules/catalog/AliasCandidatesPanel'

const aliasCandidates = vi.fn()
const acceptAliasCandidate = vi.fn()
const ignoreAliasCandidate = vi.fn()
const resolveProperty = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    aliasCandidates: (...args: unknown[]) => aliasCandidates(...args),
    acceptAliasCandidate: (...args: unknown[]) => acceptAliasCandidate(...args),
    ignoreAliasCandidate: (...args: unknown[]) => ignoreAliasCandidate(...args),
    resolveProperty: (...args: unknown[]) => resolveProperty(...args),
  },
}))

const ROW = {
  id: 'c1',
  kind: 'property',
  text: 'UTS',
  source: 'search',
  count: 3,
  status: 'open',
  resolved_to: null,
  first_seen_at: '2026-09-16T00:00:00Z',
  last_seen_at: '2026-09-16T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  aliasCandidates.mockResolvedValue([ROW])
  acceptAliasCandidate.mockResolvedValue({ ...ROW, status: 'accepted' })
  ignoreAliasCandidate.mockResolvedValue({ ...ROW, status: 'ignored' })
  resolveProperty.mockResolvedValue({
    query: '인장',
    ambiguous: false,
    candidates: [
      { key: 'mechanical.tensile_strength', name: '인장강도', deprecated: false },
      { key: 'mechanical.old', name: '옛 인장강도', deprecated: true },
    ],
  })
})

describe('별칭 후보', () => {
  it('이름으로 찾은 물성을 고르면 그 키로 받아들인다 — 폐기된 키는 후보에 없다', async () => {
    const user = userEvent.setup()
    render(<AliasCandidatesPanel />)
    expect(await screen.findByText('UTS')).toBeInTheDocument()
    await user.type(screen.getByLabelText('UTS 의 물성'), '인장')
    await user.click(await screen.findByRole('button', { name: /인장강도/ }))
    await waitFor(() =>
      expect(acceptAliasCandidate).toHaveBeenCalledWith('c1', 'mechanical.tensile_strength'),
    )
    expect(screen.queryByText('옛 인장강도')).toBeNull()
    // 판정 뒤 목록을 다시 읽는다 — 다시 읽기는 판정이 끝나고 다시 그린 뒤라 기다린다.
    await waitFor(() => expect(aliasCandidates).toHaveBeenCalledTimes(2))
  })

  it('무시는 그 줄만', async () => {
    const user = userEvent.setup()
    render(<AliasCandidatesPanel />)
    await user.click(await screen.findByRole('button', { name: '무시' }))
    await waitFor(() => expect(ignoreAliasCandidate).toHaveBeenCalledWith('c1'))
    expect(acceptAliasCandidate).not.toHaveBeenCalled()
  })

  it('남은 것이 없으면 그렇게 말한다', async () => {
    aliasCandidates.mockResolvedValue([])
    render(<AliasCandidatesPanel />)
    expect(await screen.findByText(/남은 것이 없습니다/)).toBeInTheDocument()
  })
})

describe('이것 아닐까', () => {
  it('서버가 짐작한 후보를 누르면 그대로 별칭이 된다', async () => {
    // 못 푼 이름이야말로 뜻 검색이 제일 잘 하는 일이다 — 전에는 이름만 쌓이고
    // 관리자가 물성 271개에서 스스로 떠올려야 했다(2026-09-18).
    aliasCandidates.mockResolvedValue([
      {
        id: 'c-9',
        kind: 'property',
        text: '비캣 연화온도',
        source: 'resolve',
        count: 3,
        status: 'open',
        resolved_to: null,
        first_seen_at: '2026-09-18T00:00:00Z',
        last_seen_at: '2026-09-18T00:00:00Z',
        suggestions: [
          {
            key: 'thermal.vicat_softening',
            name: '비카트 연화온도',
            si_unit: 'K',
            value_count: 34,
            matched_by: 'meaning',
          },
        ],
      },
    ])
    acceptAliasCandidate.mockResolvedValue({})
    render(<AliasCandidatesPanel />)
    const chip = await screen.findByRole('button', { name: /비카트 연화온도/ })
    await userEvent.click(chip)
    await waitFor(() =>
      expect(acceptAliasCandidate).toHaveBeenCalledWith('c-9', 'thermal.vicat_softening')
    )
  })
})
