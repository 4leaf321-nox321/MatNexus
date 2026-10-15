/**
 * 선언 값 승인 요청(2026-10-15) — **기다리는 값이 있을 때만** 서고, 보낸 결과를 창 안에서 말한다.
 *
 * 판정은 서버 `declared_approval.waiting` 과 같다: 승인 전이고, 승인하면 등급이 오르는 줄.
 * 규격 값처럼 승인해도 그대로인 줄을 세면 「3건」 이라는데 「승인 대기 값」 화면에는 2건이 뜬다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeclaredApprovalAsk, waitingCount } from '@/modules/materials/DeclaredApprovalAsk'
import type { DeclaredProperty, Material } from '@/modules/materials/api'

const requestDeclaredApproval = vi.fn()
vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    requestDeclaredApproval: (...args: unknown[]) => requestDeclaredApproval(...args),
  },
}))

function row(over: Partial<DeclaredProperty> = {}): DeclaredProperty {
  return {
    item: '탄성계수',
    points: [{ value_si: 200e9, temperature_k: null }],
    source: 'literature',
    reference: 'ASM Handbook',
    quality_tier: 3,
    tier_if_approved: 2,
    approval: null,
    ...over,
  } as DeclaredProperty
}

function material(rows: DeclaredProperty[]): Material {
  return { id: 'm1', record_name: 'SECC_MDOI_1.0', declared_properties: rows } as Material
}

beforeEach(() => {
  requestDeclaredApproval.mockReset()
})

describe('기다리는 값 세기', () => {
  it('승인 전이고 승인하면 오르는 줄만 센다', () => {
    expect(
      waitingCount([
        row(),
        // 승인됨 — 이미 끝났다.
        row({ item: '밀도', approval: { by: '관리자', at: '2026-10-01T00:00:00Z' } } as never),
        // 규격 — 승인해도 2 그대로다.
        row({ item: '푸아송비', source: 'standard', quality_tier: 2, tier_if_approved: 2 }),
      ])
    ).toBe(1)
  })
})

describe('승인 요청', () => {
  it('기다리는 값이 없으면 서지 않는다', () => {
    const { container } = render(
      <DeclaredApprovalAsk material={material([row({ quality_tier: 2, tier_if_approved: 2 })])} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('보내면 서버가 센 수와 받은 사람 수를 말한다', async () => {
    requestDeclaredApproval.mockResolvedValue({ pending: 2, notified: 1 })
    render(<DeclaredApprovalAsk material={material([row()])} />)
    expect(screen.getByText('1건')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '승인 요청' }))
    await userEvent.type(screen.getByLabelText('남길 말'), '원문 p.120')
    await userEvent.click(screen.getByRole('button', { name: '요청 보내기' }))

    // 화면은 재료 쪽만 셌고 서버는 시료 값까지 센다 — 서버의 수를 믿는다.
    expect(
      await screen.findByText('승인 대기 2건 — 자료 관리자 1명에게 알렸습니다.')
    ).toBeInTheDocument()
    expect(requestDeclaredApproval).toHaveBeenCalledWith('m1', '원문 p.120')
  })
})
