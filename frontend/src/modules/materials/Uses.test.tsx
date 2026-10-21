/**
 * 용도 목록 — **어디까지가 한 항목인가.**
 *
 * 쉼표로 이으면 그 경계가 안 보인다. 「이너 패널, 아우터 패널, 리인포스먼트…」 가
 * 열 개쯤 이어지면 눈이 쉼표를 세게 되고, 값 자체에 띄어쓰기가 있어서 더 그렇다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Uses } from '@/modules/materials/MaterialDetailPage'

describe('용도 목록', () => {
  it('항목마다 제 배지를 갖는다', () => {
    render(<Uses items={['이너 패널', '아우터 패널', '리인포스먼트']} />)
    expect(screen.getByText('이너 패널')).toBeInTheDocument()
    expect(screen.getByText('아우터 패널')).toBeInTheDocument()
    // **한 덩이로 이어 붙이지 않는다.**
    expect(screen.queryByText(/이너 패널, 아우터 패널/)).not.toBeInTheDocument()
  })

  it('비어 있으면 그렇다고 적는다', () => {
    // 빈칸으로 두면 「안 적었다」 와 「못 봤다」 가 안 갈린다.
    render(<Uses items={[]} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('많으면 앞의 몇 개와 나머지 수만 보인다', () => {
    // 부품 50개가 배지로 늘어서면 재료 머리가 화면을 다 먹는다(ADR 0064).
    render(<Uses items={Array.from({ length: 50 }, (_, index) => `파트 ${index}`)} max={8} />)
    expect(screen.getByText('파트 7')).toBeInTheDocument()
    expect(screen.queryByText('파트 8')).not.toBeInTheDocument()
    expect(screen.getByText('외 42개')).toBeInTheDocument()
  })

  it('값이 없어도 터지지 않는다', () => {
    render(<Uses />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
