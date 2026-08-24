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
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  GLOBAL,
  ownersIn,
  TestTypeFilterPanel,
  testTypesIn,
} from '@/modules/tests/TestTypeFilterPanel'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const ROWS = [
  { test_type_key: 'tensile', test_type_label: '인장시험' },
  { test_type_key: 'tensile', test_type_label: '인장시험' },
  { test_type_key: 'dma_sweep', test_type_label: 'DMA 스윕' },
]

/** 소유가 붙은 것들. 전역 하나와 부서 둘. */
const OWNED = [
  { test_type_key: 'tensile', test_type_label: '인장시험', is_global: true },
  {
    test_type_key: 'tensile',
    test_type_label: '인장시험',
    is_global: false,
    owner_workspace_name: '금속재료팀',
  },
  {
    test_type_key: 'dma_sweep',
    test_type_label: 'DMA 스윕',
    is_global: false,
    owner_workspace_name: '고분자팀',
  },
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

describe('부서 축', () => {
  beforeEach(() => {
    // 켜짐 상태가 브라우저에 남으므로 시험끼리 새면 안 된다.
    window.localStorage.clear()
  })

  it('전역을 먼저 세운다', () => {
    // 모든 부서가 쓰는 것이라 목록의 뿌리에 가깝다.
    expect(ownersIn(OWNED).map((o) => o.label)).toEqual([GLOBAL, '고분자팀', '금속재료팀'])
  })

  it('안 주면 축 자체가 없다', () => {
    // **파일 형식처럼 소유가 없는 목록에서는 켤 것도 없다.**
    render(
      <LeftPanelProvider>
        <LeftPanelHost />
        <TestTypeFilterPanel label="프로파일 종류" rows={ROWS} current={null} onPick={vi.fn()} />
      </LeftPanelProvider>
    )
    expect(screen.queryByRole('button', { name: /부서로 나누기/ })).not.toBeInTheDocument()
  })

  it('기본은 꺼져 있다', () => {
    // **부서가 하나뿐인 조직에서는 늘 한 줄짜리 소음이다.**
    owned()
    expect(screen.getByRole('button', { name: /부서로 나누기/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
    expect(screen.queryByRole('button', { name: /금속재료팀/ })).not.toBeInTheDocument()
  })

  it('켜면 부서가 개수와 함께 나온다', async () => {
    owned()
    await userEvent.click(screen.getByRole('button', { name: /부서로 나누기/ }))
    expect(screen.getByRole('button', { name: /금속재료팀/ })).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: new RegExp(GLOBAL.replace(/[()]/g, '\$&')) }))
      .toBeInTheDocument()
  })

  it('부서를 고르면 그 이름을 넘긴다', async () => {
    const onPickOwner = vi.fn()
    owned(null, onPickOwner)
    await userEvent.click(screen.getByRole('button', { name: /부서로 나누기/ }))
    await userEvent.click(screen.getByRole('button', { name: /고분자팀/ }))
    expect(onPickOwner).toHaveBeenCalledWith('고분자팀')
  })

  it('끄면 걸어 둔 필터를 푼다', async () => {
    // **안 풀면 안 보이는 필터가 걸린 채로 남고**, 목록이 왜 짧은지 알 수 없다.
    const onPickOwner = vi.fn()
    owned('금속재료팀', onPickOwner)
    const toggle = screen.getByRole('button', { name: /부서로 나누기/ })
    await userEvent.click(toggle)  // 켠다
    await userEvent.click(toggle)  // 끈다
    expect(onPickOwner).toHaveBeenLastCalledWith(null)
  })

  it('켠 상태가 다음에도 남는다', async () => {
    // 부서가 여럿인 조직에서는 매번 켜는 것이 그 자체로 일이다.
    const first = owned()
    await userEvent.click(screen.getByRole('button', { name: /부서로 나누기/ }))
    first.unmount()

    owned()
    expect(screen.getByRole('button', { name: /부서로 나누기/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  })
})

function owned(owner: string | null = null, onPickOwner = vi.fn()) {
  return render(
    <LeftPanelProvider>
      <LeftPanelHost />
      <TestTypeFilterPanel
        label="레시피 종류"
        rows={OWNED}
        current={null}
        onPick={vi.fn()}
        owner={owner}
        onPickOwner={onPickOwner}
        ownerKey="시험용"
      />
    </LeftPanelProvider>
  )
}
