/**
 * 사업부별 현황 — **순서는 서버가 정하고, 화면은 다시 정렬하지 않는다.**
 *
 * 무는 자리를 「그래프가 그려진다」 보다 **「표와 범례가 같은 순서」**·「그 해에 안
 * 한 것과 0건이 구별된다」 에 둔다. 앞엣것은 눈에 보이지만, 뒤엣것은 색이 밀려
 * 조용히 다른 사업부로 읽힌다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DivisionPanel } from '@/modules/statistics/DivisionPanel'
import { divisionRank, yearRows } from '@/modules/statistics/divisionColors'
import type { DivisionOverview } from '@/modules/statistics/api'

const DATA: DivisionOverview = {
  divisions: [
    { division: 'MX', run_count: 45, specimen_count: 30, sample_count: 12, material_count: 8 },
    { division: 'VD', run_count: 26, specimen_count: 18, sample_count: 9, material_count: 6 },
    { division: '미지정', run_count: 3, specimen_count: 2, sample_count: 1, material_count: 1 },
  ],
  yearly: [
    { year: 2025, division: 'MX', run_count: 20 },
    { year: 2026, division: 'MX', run_count: 25 },
    { year: 2026, division: 'VD', run_count: 26 },
    { year: 2026, division: '미지정', run_count: 3 },
  ],
}

describe('DivisionPanel', () => {
  it('서버가 준 순서 그대로 — 화면이 다시 정렬하지 않는다', () => {
    render(<DivisionPanel data={DATA} loading={false} />)
    const names = screen
      .getAllByRole('row')
      .slice(1) // 머리글 제외
      .map((row) => row.querySelector('td')?.textContent?.trim())
    expect(names).toEqual(['MX', 'VD', '미지정'])
  })

  it('미지정도 보인다 — 숨기면 채울 일이 안 보인다', () => {
    render(<DivisionPanel data={DATA} loading={false} />)
    expect(screen.getByText('미지정')).toBeInTheDocument()
  })

  it('데이터가 없으면 아무것도 안 그린다', () => {
    const { container } = render(
      <DivisionPanel data={{ divisions: [], yearly: [] }} loading={false} />
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('divisionRank', () => {
  it('MX · VD · DA · NW · 의료기기 순, 모르는 값은 뒤, 미지정은 맨 뒤', () => {
    const shuffled = ['의료기기', '미지정', 'DA', '신규사업', 'MX', 'NW', 'VD']
    const sorted = [...shuffled].sort((a, b) => {
      const [ai, an] = divisionRank(a)
      const [bi, bn] = divisionRank(b)
      return ai - bi || an.localeCompare(bn)
    })
    expect(sorted).toEqual(['MX', 'VD', 'DA', 'NW', '의료기기', '신규사업', '미지정'])
  })
})

describe('yearRows', () => {
  it('한 해가 한 줄이고, 합계를 함께 담는다', () => {
    expect(yearRows(DATA.yearly)).toEqual([
      { year: '2025', 합계: 20, MX: 20 },
      { year: '2026', 합계: 54, MX: 25, VD: 26, 미지정: 3 },
    ])
  })

  it('그 해에 없던 사업부는 키를 안 만든다 — 0 과 구별된다', () => {
    // 2025 에 VD 키가 있으면 범례에 서고 툴팁에 「0건」 이 뜬다.
    expect('VD' in yearRows(DATA.yearly)[0]).toBe(false)
  })

  it('해는 오름차순 — 위에서 아래로 시간이 흐른다', () => {
    const shuffled = [...DATA.yearly].reverse()
    expect(yearRows(shuffled).map((row) => row.year)).toEqual(['2025', '2026'])
  })

  it('비면 빈 줄 — 그래프가 「아직 시험이 없습니다」 를 보인다', () => {
    expect(yearRows([])).toEqual([])
  })
})
