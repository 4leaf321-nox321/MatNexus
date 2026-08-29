/**
 * 화면 머리글 — **긴 화면에서 「지금 무엇을 보고 있나」 를 잃지 않는가.**
 *
 * 시험 상세는 곡선·요약값·처리 단계·결과가 탭마다 쌓여 길다. 아래로 내려가면
 * 제목과 재료가 화면에서 사라지고, 곡선만 남으면 **그것이 어느 시험의 곡선인지
 * 알 수 없다** — 되돌아가는 단추도 함께 사라진다.
 *
 * jsdom 에는 스크롤이 없으니 「붙어 있다」 는 못 잰다. 대신 **켠 화면과 안 켠
 * 화면이 실제로 다른가**를 문다 — 기본이 조용히 켜지면 짧은 화면이 세로를
 * 잃고, 반대로 스위치가 안 먹으면 이 화면이 옛 모습 그대로 남는다.
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { PageHeader } from '@/shared/components/PageHeader'

function box(sticky: boolean) {
  const { container } = render(
    <MemoryRouter>
      <PageHeader title="SECC_1.0-MD-1" sticky={sticky} />
    </MemoryRouter>
  )
  return container.firstElementChild as HTMLElement
}

describe('머리글 고정', () => {
  it('켜면 스크롤에서 빠진다', () => {
    expect(box(true).className).toContain('sticky')
  })

  it('기본은 안 켠다 — 짧은 화면은 세로만 잃는다', () => {
    expect(box(false).className).not.toContain('sticky')
  })

  it('켜도 제목은 그대로 읽힌다', () => {
    render(
      <MemoryRouter>
        <PageHeader title="SECC_1.0-MD-1" description="인장 · SECC" sticky />
      </MemoryRouter>
    )
    expect(screen.getByRole('heading', { name: 'SECC_1.0-MD-1' })).toBeInTheDocument()
    expect(screen.getByText('인장 · SECC')).toBeInTheDocument()
  })
})
