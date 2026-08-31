import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RecordName } from '@/shared/components/RecordName'

describe('RecordName', () => {
  it('글자는 하나도 안 바뀐다', () => {
    // **여기가 핵심이다.** 감추면 보이는 이름과 저장된 이름이 갈라지고, 검색은
    // 저장된 이름으로 걸리므로 보이는 대로 쳐서는 안 찾힌다.
    const { container } = render(<RecordName name="SECC_-_1.0__02__MD_03" />)
    expect(container.textContent).toBe('SECC_-_1.0__02__MD_03')
  })

  it('빈 칸만 흐려진다', () => {
    render(<RecordName name="SECC_-_1.0" />)
    const blank = screen.getByTitle('값이 없는 칸')
    expect(blank.textContent).toBe('-')
  })

  it('값 안의 붙임표는 안 건드린다', () => {
    // `DP-590` 은 값이지 빈 칸이 아니다 — 칸 전체가 `-` 일 때만 빈 칸이다.
    render(<RecordName name="DP-590_MDOI_1.0" />)
    expect(screen.queryByTitle('값이 없는 칸')).toBeNull()
  })

  it('빈 칸이 둘이면 둘 다', () => {
    render(<RecordName name="SECC_-_-" />)
    expect(screen.getAllByTitle('값이 없는 칸')).toHaveLength(2)
  })

  it('빈 칸이 없으면 그대로', () => {
    const { container } = render(<RecordName name="SECC_MDOI_1.0" />)
    expect(container.textContent).toBe('SECC_MDOI_1.0')
    expect(screen.queryByTitle('값이 없는 칸')).toBeNull()
  })
})
