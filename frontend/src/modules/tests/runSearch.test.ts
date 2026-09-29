/**
 * 시험 상세 조건 → 서버 질의 — **조건 값은 화면 단위로, 단위를 함께.**
 *
 * 온도는 °C 로 친다. 단위 없이 80 을 보내면 서버가 거절하고, 짐작하면 80 K 가 되어 조용히
 * 틀린다. 단위는 표(`shared/units`)에서 읽는다 — 라벨과 보내는 단위가 한 곳에서 온다.
 */

import { describe, expect, it } from 'vitest'

import {
  EMPTY_RUN_DETAIL,
  conditionUnit,
  runDetailCount,
  runDetailQuery,
} from '@/modules/tests/runSearch'
import { display } from '@/shared/units'

const STANDARDS = [
  { key: 'temperature', si_unit: 'K' },
  { key: 'strain_rate', si_unit: '1/s' },
  { key: 'humidity', si_unit: '1' },
]

describe('runDetailQuery', () => {
  it('조건 범위는 표의 화면 단위를 함께 싣는다', () => {
    expect(
      runDetailQuery(
        { ...EMPTY_RUN_DETAIL, condition: 'temperature', conditionMin: '70', conditionMax: '90' },
        STANDARDS
      )
    ).toEqual({
      condition: 'temperature',
      condition_unit: display('K').unit,
      condition_min: '70',
      condition_max: '90',
    })
  })

  it('범위를 안 적었거나 모르는 조건이면 조건을 싣지 않는다', () => {
    // 고르기만 하고 범위가 없으면 서버가 거절한다 — 사람에게는 「골랐는데 오류」 로 보인다.
    expect(runDetailQuery({ ...EMPTY_RUN_DETAIL, condition: 'temperature' }, STANDARDS)).toEqual(
      {}
    )
    expect(
      runDetailQuery({ ...EMPTY_RUN_DETAIL, condition: 'unknown', conditionMin: '1' }, STANDARDS)
    ).toEqual({})
  })

  it('기간·장비는 그대로 싣고 빈 칸은 뺀다', () => {
    expect(
      runDetailQuery(
        { ...EMPTY_RUN_DETAIL, testedFrom: '2026-04-01', instrument: 'Zwick Z100' },
        STANDARDS
      )
    ).toEqual({ tested_from: '2026-04-01', instrument: 'Zwick Z100' })
  })
})

describe('conditionUnit', () => {
  it('표에 화면 단위가 없으면 SI 그대로 — 무차원은 1', () => {
    expect(conditionUnit({ si_unit: 'K' })).toBe(display('K').unit)
    expect(conditionUnit({ si_unit: '1' })).toBe('1')
  })
})

describe('runDetailCount', () => {
  it('걸린 질의에서 세고, 기간은 끝이 둘이어도 하나다', () => {
    expect(runDetailCount({})).toBe(0)
    expect(runDetailCount({ tested_from: '2026-01-01', tested_to: '2026-02-01' })).toBe(1)
    expect(runDetailCount({ instrument: 'Z', condition: 'temperature', q: 'SECC' })).toBe(2)
  })
})
