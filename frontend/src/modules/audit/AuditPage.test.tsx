/**
 * 변경 이력 화면.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   고치는 단추가 없다        고칠 수 있으면 감사가 아니다
 *   모르는 코드도 안 감춘다   모르는 일이 일어났다는 것 자체가 알아야 할 일이다
 *   지워진 계정을 짚는다      id 는 비고 이름만 남는다 — 그 사실이 보여야 한다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

/**
 * **표가 그려질 때까지 기다리고, 그 안에서 찾는다.**
 *
 * 행위 이름(「물성 카드 확정」)은 위쪽 「행위로 필터」 에도 `<option>` 으로 늘 있다. 그래서
 * `findByText` 로 기다리면 표가 아니라 그 옵션이 먼저 잡혀 **아무것도 안 기다린다** — 바로
 * 뒤의 동기 검사가 목록 응답과 경주했다. CI 에서 실제로 졌다(2026-09-24, 배지를 못 찾음).
 * 응답을 50ms 늦추면 매번 진다 — 그리고 「단추가 없다」 는 빈 화면에서 틀린 이유로 통과했다.
 */
async function table() {
  return within(await screen.findByRole('table'))
}

describe('변경 이력', () => {
  it('행위를 사람이 읽는 말로 보인다', async () => {
    render(<AuditPage />)
    const rows = await table()
    expect(rows.getByText('물성 카드 확정')).toBeInTheDocument()
    expect(rows.getByText('DP600 MD')).toBeInTheDocument()
  })

  it('모르는 코드도 감추지 않는다', async () => {
    // **모르는 일이 일어났다는 것 자체가 알아야 할 일이다.**
    list.mockResolvedValue([entry({ action: 'creep.calibrated' })])
    render(<AuditPage />)
    expect(await screen.findByText('creep.calibrated')).toBeInTheDocument()
  })

  it('바뀐 것을 전후로 보인다', async () => {
    render(<AuditPage />)
    // **화면을 기다린다.** 전에는 `list` 가 불렸는지만 기다렸는데, 불린 것과
    // 응답이 온 것과 React 가 다시 그린 것은 서로 다른 순간이다 - 머신이
    // 바쁘면 그 사이가 벌어져 아직 안 그려진 화면에 대고 검사하게 된다.
    expect(await screen.findByText('draft')).toBeInTheDocument()
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
    // **없는 것을 검사할 때가 더 위험하다.** 안 그려진 화면에서는 무엇이든
    // 없으므로, 기다리지 않으면 **틀린 이유로 통과한다.**
    await table()
    for (const name of [/생성/, /추가/, /편집/, /삭제/, /삭제/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })

  it('비어 있으면 어디서 생기는지 말한다', async () => {
    list.mockResolvedValue([])
    render(<AuditPage />)
    expect(await screen.findByText(/물성 카드를 확정하거나 내리면/)).toBeInTheDocument()
  })
})

describe('들어온 길', () => {
  it('AI 가 거친 것만 골라 볼 수 있다', async () => {
    // **권한은 언제나 그 사람의 것이라** `누가` 열만으로는 안 갈린다. 반년 뒤에
    // 물어지는 것은 「이거 사람이 확인한 거 맞나」 다.
    const user = userEvent.setup()
    render(<AuditPage />)
    await table()
    await user.selectOptions(screen.getByLabelText('들어온 길로 필터'), 'mcp')
    await waitFor(() => expect(list).toHaveBeenCalledWith({ client: 'mcp' }))
  })

  it('AI 가 쓴 것이 없으면 그렇게 말한다', async () => {
    // 「기록이 없다」 와 「AI 가 아직 아무것도 안 썼다」 는 다른 말이다 —
    // 거른 결과가 비었을 때 앞의 말만 하면 거른 줄을 잊는다.
    const user = userEvent.setup()
    render(<AuditPage />)
    await table()
    list.mockResolvedValue([])
    await user.selectOptions(screen.getByLabelText('들어온 길로 필터'), 'mcp')
    expect(await screen.findByText(/아직 AI 가 쓴 적이 없다는 뜻/)).toBeInTheDocument()
  })

  it('AI 가 한 일도 사람이 읽는 말로 보인다', async () => {
    list.mockResolvedValue([
      entry({ action: 'card.created_by_client', client: 'mcp', actor_label: '홍길동' }),
    ])
    render(<AuditPage />)
    const rows = await table()
    expect(rows.getByText('AI 가 물성 카드 생성')).toBeInTheDocument()
    // 배지로 짚는다 — 같은 말이 위쪽 「경로」 고르개에도 있다.
    expect(rows.getByTitle(/AI\(MCP\) 를 거쳐 한 일입니다/)).toBeInTheDocument()
  })
})
