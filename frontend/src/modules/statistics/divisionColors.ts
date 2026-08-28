/**
 * 사업부 색과 연도 접기 — **표와 그래프가 같은 것을 쓴다.**
 *
 * 색을 양쪽이 따로 정하면 표의 점과 그래프의 막대가 다른 색이 되고, 그때 사람은
 * 둘을 다른 사업부로 읽는다. 그래프는 늦게 오는 조각(`DivisionYearChart`)이라
 * 공통은 여기 둔다 — 이 파일은 가볍다.
 */

import type { DivisionOverview } from '@/modules/statistics/api'

/**
 * 사업부 차례 — **서버(`app/shared/divisions.py`)와 같은 값.**
 *
 * 서버가 목록을 이 차례로 주므로 화면은 대개 다시 정렬할 필요가 없다. 다만
 * recharts 의 툴팁처럼 **우리가 순서를 못 넘기는 자리**가 있어, 거기서 쓸 차례를
 * 여기 둔다. 두 벌이 된 것은 알고 있다 — 기준정보에 순서 칸이 생기면 둘 다 그것을
 * 읽는다.
 */
export const DIVISION_ORDER = ['MX', 'VD', 'DA', 'NW', '의료기기'] as const
export const UNSET_DIVISION = '미지정'

/** 정렬 열쇠. 모르는 값은 뒤에 이름순, 「미지정」 은 맨 뒤. */
export function divisionRank(division: string): [number, string] {
  if (division === UNSET_DIVISION) return [DIVISION_ORDER.length + 1, '']
  const at = DIVISION_ORDER.indexOf(division as (typeof DIVISION_ORDER)[number])
  return at >= 0 ? [at, ''] : [DIVISION_ORDER.length, division]
}

/** 순서는 서버가 주는 순서 그대로 쓰고, 색만 여기서 돌려 쓴다. */
const PALETTE = ['#2563eb', '#16a34a', '#f59e0b', '#9333ea', '#dc2626', '#0891b2']
const UNSET_COLOR = '#9ca3af'

export function colorOf(division: string, order: string[]): string {
  if (division === '미지정') return UNSET_COLOR
  const at = order.indexOf(division)
  return PALETTE[(at >= 0 ? at : order.length) % PALETTE.length]
}

export interface YearRow {
  year: string
  합계: number
  [division: string]: number | string
}

/**
 * 서버가 준 (해, 사업부, 건수) 를 **한 해 한 줄**로 접는다. 누적 막대가 그 모양을
 * 받는다. 해는 오름차순 — 위에서 아래로 시간이 흐른다.
 *
 * 빠진 사업부는 **키를 안 만든다.** 0 을 넣으면 범례에 서고 툴팁에 「0건」 이 뜬다 —
 * 그 해에 안 한 것과 0건 한 것은 화면에서 같아 보이면 안 된다.
 */
export function yearRows(yearly: DivisionOverview['yearly']): YearRow[] {
  const years = [...new Set(yearly.map((row) => row.year))].sort((a, b) => a - b)
  return years.map((year) => {
    const mine = yearly.filter((one) => one.year === year)
    const row: YearRow = {
      year: String(year),
      합계: mine.reduce((sum, one) => sum + one.run_count, 0),
    }
    for (const one of mine) row[one.division] = one.run_count
    return row
  })
}
