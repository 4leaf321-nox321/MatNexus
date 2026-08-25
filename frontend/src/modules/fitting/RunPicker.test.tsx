/**
 * 카드에 쓸 시험 고르기.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   기본은 전부           안 건드리면 전과 똑같이 만들어진다(`null`)
 *   이상치는 표시만        버리는 것은 사람이 정한다
 *   전부 켜면 다시 `null`  「고르지 않음」과 「전부 고름」은 같은 뜻이다
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RunPicker } from '@/modules/fitting/RunPicker'
import type { RunChoice } from '@/modules/fitting/RunPicker'

const RUNS: RunChoice[] = [
  { id: 'r-1', name: 'SECC__01__MD_01__TEN_01', flags: [] },
  { id: 'r-2', name: 'SECC__02__MD_01__TEN_01', flags: ['인장강도'] },
  { id: 'r-3', name: 'SECC__03__MD_01__TEN_01', flags: [] },
]

function draw(used: string[] | null = null, onChange = vi.fn()) {
  render(<RunPicker runs={RUNS} used={used} onChange={onChange} />)
  return onChange
}

describe('쓸 시험 고르기', () => {
  it('안 건드리면 전부 켜져 있다', () => {
    draw()
    for (const run of RUNS) {
      expect(screen.getByLabelText(`${run.name} 쓰기`)).toBeChecked()
    }
    expect(screen.getByText('3 / 3건')).toBeInTheDocument()
  })

  it('이상치 후보에 표를 단다', () => {
    // **버리지 않는다.** 통계 화면과 같은 규칙이다 — 자동으로 빼면 n 이 왜 그
    // 수인지 카드를 보는 사람이 알 수 없다.
    draw()
    expect(screen.getByText('인장강도')).toBeInTheDocument()
    expect(screen.getByLabelText(`${RUNS[1].name} 쓰기`)).toBeChecked()
  })

  it('하나를 빼면 나머지 목록으로 알린다', () => {
    const onChange = draw()
    fireEvent.click(screen.getByLabelText(`${RUNS[1].name} 쓰기`))
    expect(onChange).toHaveBeenCalledWith(['r-1', 'r-3'])
  })

  it('전부 켜면 다시 「고르지 않음」이 된다', () => {
    // 그래야 요청에 목록이 안 실리고, 안 골랐다는 사실이 카드 근거에 남는다.
    const onChange = draw(['r-1', 'r-3'])
    fireEvent.click(screen.getByLabelText(`${RUNS[1].name} 쓰기`))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('이상치 후보를 한 번에 뺀다', () => {
    // 하나씩 누르게 하면 열 건에서 그것 자체가 일이 된다.
    const onChange = draw()
    fireEvent.click(screen.getByRole('button', { name: /이상치 후보 1건 빼기/ }))
    expect(onChange).toHaveBeenCalledWith(['r-1', 'r-3'])
  })

  it('몇 건을 뺐는지와 무엇이 안 바뀌는지 말한다', () => {
    // **채택은 그대로다.** 그것을 말해 주지 않으면, 사람은 이 체크박스가
    // 채택을 푸는 것이라고 읽는다.
    draw(['r-1'])
    expect(screen.getByText(/2건을 뺐습니다/)).toBeInTheDocument()
    expect(screen.getByText(/채택은 그대로라/)).toBeInTheDocument()
  })

  it('전부 되돌릴 수 있다', () => {
    const onChange = draw(['r-1'])
    fireEvent.click(screen.getByRole('button', { name: '전부 되돌리기' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })
})
