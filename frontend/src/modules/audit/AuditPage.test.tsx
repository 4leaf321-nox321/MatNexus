/**
 * 감사 기록 화면.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   고치는 단추가 없다        고칠 수 있으면 감사가 아니다
 *   모르는 코드도 안 감춘다   모르는 일이 일어났다는 것 자체가 알아야 할 일이다
 *   지워진 계정을 짚는다      id 는 비고 이름만 남는다 — 그 사실이 보여야 한다
 */

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AuditPage from '@/modules/audit/AuditPage'

const list = vi.fn()

vi.mock('@/modules/audit/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/audit/api')>()),
  auditApi: { list: (...args: unknown[]) => list(...args) },
}))

function entry(overrides: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    action: 'card.published',
    actor_id: 'u1',
    actor_label: '홍길동',
    target_table: 'property_cards',
    target_id: 'c1',
    target_label: 'DP600 MD',
    workspace_id: null,
    changes: { status: { before: 'draft', after: 'published' } },
    reason: null,
    request_id: 'abc123',
    created_at: '2026-08-23T10:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  list.mockResolvedValue([entry()])
})

describe('감사 기록', () => {
  it('행위를 사람이 읽는 말로 보인다', async () => {
    render(<AuditPage />)
    expect(await screen.findByText('물성 카드 확정')).toBeInTheDocument()
    expect(screen.getByText('DP600 MD')).toBeInTheDocument()
  })

  it('모르는 코드도 감추지 않는다', async () => {
    // **모르는 일이 일어났다는 것 자체가 알아야 할 일이다.**
    list.mockResolvedValue([entry({ action: 'creep.calibrated' })])
    render(<AuditPage />)
    expect(await screen.findByText('creep.calibrated')).toBeInTheDocument()
  })

  it('바뀐 것을 전후로 보인다', async () => {
    render(<AuditPage />)
    await waitFor(() => expect(list).toHaveBeenCalled())
    expect(screen.getByText('draft')).toBeInTheDocument()
    expect(screen.getByText('published')).toBeInTheDocument()
  })

  it('지워진 계정을 짚는다', async () => {
    // 계정이 지워지면 id 는 비고 이름만 남는다 — 그 사실이 보여야 한다.
    list.mockResolvedValue([entry({ actor_id: null, actor_label: '홍길동' })])
    render(<AuditPage />)
    expect(await screen.findByText('(지워진 계정)')).toBeInTheDocument()
  })

  it('고치는 단추가 없다', async () => {
    // **고칠 수 있으면 감사가 아니다.**
    render(<AuditPage />)
    await waitFor(() => expect(list).toHaveBeenCalled())
    for (const name of [/만들기/, /추가/, /고치기/, /지우기/, /삭제/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })

  it('비어 있으면 어디서 생기는지 말한다', async () => {
    list.mockResolvedValue([])
    render(<AuditPage />)
    expect(await screen.findByText(/물성 카드를 확정하거나 내리면/)).toBeInTheDocument()
  })
})
