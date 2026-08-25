/**
 * 생성 날짜 — **제목 옆에서 보여야 한다.**
 *
 * 물성에는 그 물음이 늘 따라 붙는다: 어느 로트인가, 언제 잰 것인가, 이 카드가
 * 지난달 것인가. 아래 표 어딘가에 적어 두면 찾아야 보이고, 찾지 않으면 모른
 * 채로 값을 읽게 된다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CreatedOn } from '@/shared/components/CreatedOn'
import { PageHeader } from '@/shared/components/PageHeader'

describe('생성 날짜', () => {
  it('날짜를 적는다', () => {
    render(<CreatedOn at="2026-08-25T01:23:45Z" />)
    expect(screen.getByText(/2026/)).toBeInTheDocument()
  })

  it('상대 시각으로 적지 않는다', () => {
    // **「3일 전」은 읽는 시점에 따라 달라진다.** 화면을 캡처해 주고받는 순간
    // 그 말은 뜻을 잃는다 — 이 저장소의 화면은 실제로 그렇게 오간다.
    render(<CreatedOn at={new Date().toISOString()} />)
    expect(screen.queryByText(/전$|방금|오늘/)).not.toBeInTheDocument()
  })

  it('없으면 자리를 안 만든다', () => {
    // 빈 칸이 남으면 「날짜를 못 읽었다」로 보인다.
    const { container } = render(<CreatedOn at={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('제목 옆에 붙는다', () => {
    render(<PageHeader title="SECC_MDOI_1.0" created="2026-08-25T01:23:45Z" />)
    const title = screen.getByRole('heading', { name: 'SECC_MDOI_1.0' })
    // **같은 줄에 있어야 제목 옆이다.** 아래 표로 내려가면 찾아야 보인다.
    expect(title.parentElement).toHaveTextContent(/2026/)
  })

  it('생긴 방식에 맞는 말을 쓴다', () => {
    render(<CreatedOn at="2026-08-25T01:23:45Z" label="만듦" />)
    expect(screen.getByText(/만듦/)).toBeInTheDocument()
  })
})
