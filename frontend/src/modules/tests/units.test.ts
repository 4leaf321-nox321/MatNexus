/**
 * 표시 단위 — **틀리면 조용히 틀린다.**
 *
 * 단위 오류는 예외를 내지 않는다. 숫자는 멀쩡해 보이고 뜻만 바뀐다. 백엔드는
 * `tests/unit/test_units.py` 가 지키고, 화면 쪽은 여기서 지킨다.
 */

import { describe, expect, it } from 'vitest'

import {
  DIMENSIONS,
  SI_BY_DIMENSION,
  UNITS_BY_DIMENSION,
  axisLabel,
  conditionUnits,
  display,
  formatValue,
  toDisplay,
} from '@/modules/tests/units'

describe('저장 단위와 표시 단위', () => {
  it('저장은 SI, 표시는 실무 단위', () => {
    expect(display('m')).toEqual({ unit: 'mm', factor: 1000 })
    expect(display('Pa')).toEqual({ unit: 'MPa', factor: 1e-6 })
    expect(toDisplay(0.05, 'm')).toBeCloseTo(50)
  })

  it('모르는 단위는 그대로 둔다', () => {
    // 지어내면 값이 틀린다. 바꾸지 않는 편이 낫다.
    expect(display('rad/s')).toEqual({ unit: 'rad/s', factor: 1 })
  })
})

describe('변형률과 tan δ', () => {
  it('변형률은 %로 보여 준다', () => {
    expect(display('1', 'strain')).toEqual({ unit: '%', factor: 100 })
    expect(toDisplay(0.02, '1', 'strain')).toBeCloseTo(2)
  })

  it('tan δ 는 비율 그대로 둔다', () => {
    // **단위만 보면 못 가른다.** 둘 다 저장 단위가 `1` 이다. 차원이 유일한 단서고,
    // `strain` 을 `dimensionless` 의 별칭으로 남겨 둔 이유가 이것이다.
    expect(display('1', 'dimensionless')).toEqual({ unit: '', factor: 1 })
    expect(toDisplay(0.02, '1', 'dimensionless')).toBeCloseTo(0.02)
  })

  it('축 라벨에도 반영된다', () => {
    expect(axisLabel('변형률', '1', 'strain')).toBe('변형률 (%)')
    expect(axisLabel('손실계수', '1', 'dimensionless')).toBe('손실계수')
  })
})

describe('요약값 표시', () => {
  it('SI 를 실무 단위로 바꿔 적는다', () => {
    expect(formatValue(282128000, null, 'Pa')).toBe('282.13 MPa')
  })

  it('값이 없으면 원문을 보여 준다', () => {
    // 장비가 "Unknown" 이라고 적는 자리가 있다. 빈칸으로 두면 안 온 것처럼 보인다.
    expect(formatValue(null, 'Unknown', 'Pa')).toBe('Unknown')
    expect(formatValue(null, null, null)).toBe('—')
  })
})

describe('조건 단위', () => {
  it('화면이 받은 단위를 값과 함께 보낸다', () => {
    // 이것을 안 보내던 때 **6만 배** 어긋난 값이 저장됐다. 라벨은 mm/min 인데
    // 서버는 정의의 m/s 로 해석했다.
    const fields = [
      { key: 'speed', si_unit: 'm/s', dimension: 'velocity' },
      { key: 'temperature', si_unit: 'K', dimension: 'temperature' },
    ]
    expect(conditionUnits(fields)).toEqual({ speed: 'mm/min', temperature: 'K' })
  })

  it('단위 없는 항목은 안 보낸다', () => {
    expect(conditionUnits([{ key: 'note', si_unit: null }])).toEqual({})
  })
})

describe('차원 표', () => {
  it('모든 차원에 저장 단위가 있다', () => {
    // 빠지면 그 차원의 채널을 화면에서 만들 수 없다. 오류가 아니라 '목록에 없음'
    // 이라 원인을 찾기 어렵다 — `angular_frequency` 가 실제로 빠져 있었다.
    for (const dimension of DIMENSIONS) {
      expect(SI_BY_DIMENSION[dimension], dimension).toBeTruthy()
    }
    expect(SI_BY_DIMENSION.angular_frequency).toBe('rad/s')
  })

  it('고를 수 있는 단위에 저장 단위가 들어 있다', () => {
    for (const [dimension, units] of Object.entries(UNITS_BY_DIMENSION)) {
      expect(units, dimension).toContain(SI_BY_DIMENSION[dimension])
    }
  })
})
