/**
 * 선언 값 승인 요청(2026-10-15) — **서버가 센 수**로 서고, 보낸 결과를 창 안에서 말한다.
 *
 * 전에는 화면이 재료 쪽 값만 세어 서버(시료 · 밀시트까지)와 수가 갈렸다(2026-10-16 고침). 하루
 * 안에 이미 부탁했으면 누가 언제 했는지 보이고 단추를 잠근다 — 서버도 막는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeclaredApprovalAsk } from '@/modules/materials/DeclaredApprovalAsk'
import type { Material } from '@/modules/materials/api'

const requestDeclaredApproval = vi.fn()
const declaredApprovalStatus = vi.fn()
vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    requestDeclaredApproval: (...args: unknown[]) => requestDeclaredApproval(...args),
    declaredApprovalStatus: (...args: unknown[]) => declaredApprovalStatus(...args),
  },
}))

const MATERIAL = { id: 'm1', record_name: 'SECC_MDOI_1.0', declared_properties: [] } as unknown as Material

beforeEach(() => {
  requestDeclaredApproval.mockReset()
  declaredApprovalStatus.mockReset()
})

describe('승인 요청', () => {
  it('기다리는 값이 없으면 서지 않는다', async () => {
    declaredApprovalStatus.mockResolvedValue({ pending: 0, last: null, next_allowed_at: null })
    const { container } = render(<DeclaredApprovalAsk material={MATERIAL} />)
    await waitFor(() => expect(declaredApprovalStatus).toHaveBeenCalledWith('m1'))
    expect(container).toBeEmptyDOMElement()
  })

  it('서버가 센 수를 보이고, 보내면 받은 사람 수를 말한다', async () => {
    // 재료 값이 비어 있어도(시료 · 밀시트에만 있어도) 서버의 수를 믿는다.
    declaredApprovalStatus.mockResolvedValue({ pending: 2, last: null, next_allowed_at: null })
    requestDeclaredApproval.mockResolvedValue({ pending: 2, notified: 1 })
    render(<DeclaredApprovalAsk material={MATERIAL} />)
    expect(await screen.findByText('2건')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '승인 요청' }))
    await userEvent.type(screen.getByLabelText('남길 말'), '원문 p.120')
    await userEvent.click(screen.getByRole('button', { name: '요청 보내기' }))

    expect(
      await screen.findByText('승인 대기 2건 — 자료 관리자 1명에게 알렸습니다.')
    ).toBeInTheDocument()
    expect(requestDeclaredApproval).toHaveBeenCalledWith('m1', '원문 p.120')
    // 보낸 뒤 상태를 다시 읽는다 — 「요청함」 과 잠금이 서야 한다.
    await waitFor(() => expect(declaredApprovalStatus).toHaveBeenCalledTimes(2))
  })

  it('하루 안에 이미 부탁했으면 누가 언제 했는지 보이고 단추를 잠근다', async () => {
    declaredApprovalStatus.mockResolvedValue({
      pending: 1,
      last: {
        by_name: '앨리스',
        via: 'AI(MCP)',
        at: '2026-10-16T01:00:00Z',
        note: null,
        pending: 1,
      },
      next_allowed_at: '2026-10-17T01:00:00Z',
    })
    render(<DeclaredApprovalAsk material={MATERIAL} />)
    expect(await screen.findByText(/요청함 · 앨리스 · AI\(MCP\) 경유/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '승인 요청' })).toBeDisabled()
  })
})
