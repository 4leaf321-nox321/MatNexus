/**
 * 재료 상세 조건 → 서버 질의 — **무엇이 실리나.**
 *
 * 두께는 화면 단위(mm)로 보내고 단위를 함께 적어야 한다 — 단위 없이 1.2 를 보내면 서버는
 * SI 로 읽어 1.2 m 가 되고, 목록은 조용히 0건이 된다(두께 칸이 같은 자리에서 걸렸다).
 */

import { describe, expect, it } from 'vitest'

import { LENGTH_UNIT } from '@/modules/materials/api'
import {
  EMPTY_DETAIL,
  detailCount,
  detailQuery,
  sameDetail,
} from '@/modules/materials/materialSearch'

describe('detailQuery', () => {
  it('빈 칸은 싣지 않는다', () => {
    expect(detailQuery(EMPTY_DETAIL)).toEqual({})
    expect(detailQuery({ ...EMPTY_DETAIL, use: '   ' })).toEqual({})
  })

  it('두께는 화면 단위를 함께 싣고, 끝이 하나만 있어도 싣는다', () => {
    expect(detailQuery({ ...EMPTY_DETAIL, thicknessMin: '1.2' })).toEqual({
      thickness_min: 1.2,
      thickness_unit: LENGTH_UNIT,
    })
    expect(detailQuery({ ...EMPTY_DETAIL, thicknessMin: '0.8', thicknessMax: '1.6' })).toEqual({
      thickness_min: 0.8,
      thickness_max: 1.6,
      thickness_unit: LENGTH_UNIT,
    })
    // 숫자가 아니면 조건이 아니다 — `NaN` 을 보내면 서버가 0건으로 답한다.
    expect(detailQuery({ ...EMPTY_DETAIL, thicknessMin: 'abc' })).toEqual({})
  })

  it('글자 칸은 다듬어 싣고, 고르는 칸은 값 그대로', () => {
    expect(
      detailQuery({
        ...EMPTY_DETAIL,
        use: ' 범퍼 ',
        maker: '포스코',
        lot: 'L2409',
        testType: 'tensile',
        card: 'published',
        registeredFrom: '2026-01-01',
        registeredTo: '2026-03-31',
      })
    ).toEqual({
      use: '범퍼',
      maker: '포스코',
      lot: 'L2409',
      test_type: 'tensile',
      card: 'published',
      registered_from: '2026-01-01',
      registered_to: '2026-03-31',
    })
  })
})

describe('detailCount', () => {
  it('범위는 끝이 둘이어도 조건 하나로 센다', () => {
    expect(detailCount(EMPTY_DETAIL)).toBe(0)
    expect(detailCount({ ...EMPTY_DETAIL, thicknessMin: '1', thicknessMax: '2' })).toBe(1)
    expect(detailCount({ ...EMPTY_DETAIL, thicknessMax: '2' })).toBe(1)
    expect(detailCount({ ...EMPTY_DETAIL, registeredTo: '2026-01-01', use: '범퍼' })).toBe(2)
  })

  it('sameDetail 은 칸마다 견준다', () => {
    expect(sameDetail(EMPTY_DETAIL, { ...EMPTY_DETAIL })).toBe(true)
    expect(sameDetail(EMPTY_DETAIL, { ...EMPTY_DETAIL, lot: 'x' })).toBe(false)
  })
})
