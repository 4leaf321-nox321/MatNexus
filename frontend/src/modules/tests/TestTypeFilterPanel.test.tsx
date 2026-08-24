/**
 * 시험 종류 필터 옆패널 — 파일 형식과 레시피가 **같은 것을 쓴다.**
 *
 * 둘 다 시험 종류에 매달린 목록인데, `test_type_label` 을 **표에 보여만 주고
 * 거르지는 못했다** — 인장 레시피를 손보는 사람이 DMA 레시피를 눈으로 훑어
 * 넘겨야 했다.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   목록에 있는 종류만 보인다   등록된 종류 스무 개 중 열아홉이 0건이면 소음이다
 *   개수를 함께 보인다          눌러 보고 나서 0건인 걸 아는 것보다 낫다
 *   전체로 되돌아갈 수 있다     걸러 놓고 못 풀면 갇힌다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TestTypeFilterPanel, testTypesIn } from '@/modules/tests/TestTypeFilterPanel'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const ROWS = [
  { test_type_key: 'tensile', test_type_label: '인장시험' },
  { test_type_key: 'tensile', test_type_label: '인장시험' },
  { test_type_key: 'dma_sweep', test_type_label: 'DMA 스윕' },
]

function panel(current: string | null = null, onPick = vi.fn(), rows = ROWS) {
  render(
    <LeftPanelProvider>
      <LeftPanelHost />
      <TestTypeFilterPanel label="레시피 종류" rows={rows} current={current} onPick={onPick} />
    </LeftPanelProvider>
  )
  return onPick
}

describe('시험 종류 세기', () => {
  it('같은 종류를 합쳐 센다', () => {
    // 순서는 한국어 정렬이다 — `localeCompare('ko')` 는 한글을 영문보다 앞에 둔다.
    expect(testTypesIn(ROWS)).toEqual([
      { key: 'tensile', label: '인장시험', count: 2 },
      { key: 'dma_sweep', label: 'DMA 스윕', count: 1 },
    ])
  })

  it('목록에 없는 종류는 애초에 안 나온다', () => {
    // **등록된 종류 전체를 뿌리지 않는다.** 레시피가 인장에만 있으면 나머지는
    // 눌러 봐야 0건인 칸이다.
    expect(testTypesIn(ROWS).map((k) => k.key)).not.toContain('compression')
  })
})

describe('시험 종류 필터 옆패널', () => {
  it('전체와 각 종류를 개수와 함께 보인다', () => {
    panel()
    expect(screen.getByRole('button', { name: /전체/ })).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: /인장시험/ })).toHaveTextContent('2')
    expect(screen.getByRole('button', { name: /DMA 스윕/ })).toHaveTextContent('1')
  })

  it('고른 종류를 짚는다', () => {
    panel('tensile')
    expect(screen.getByRole('button', { name: /인장시험/ })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /전체/ })).not.toHaveAttribute('aria-current')
  })

  it('안 골랐으면 전체를 짚는다', () => {
    panel(null)
    expect(screen.getByRole('button', { name: /전체/ })).toHaveAttribute('aria-current', 'true')
  })

  it('누르면 그 종류를 넘긴다', async () => {
    const onPick = panel()
    await userEvent.click(screen.getByRole('button', { name: /DMA 스윕/ }))
    expect(onPick).toHaveBeenCalledWith('dma_sweep')
  })

  it('전체를 누르면 필터를 푼다', async () => {
    // **걸러 놓고 못 풀면 갇힌다.**
    const onPick = panel('tensile')
    await userEvent.click(screen.getByRole('button', { name: /전체/ }))
    expect(onPick).toHaveBeenCalledWith(null)
  })

  it('비어 있으면 왜 비었는지 말한다', () => {
    // 빈 옆패널은 고장으로 보인다.
    panel(null, vi.fn(), [])
    expect(screen.getByText(/아직 등록된 것이 없습니다/)).toBeInTheDocument()
  })
})
