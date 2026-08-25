/**
 * 표시 단위 — **틀리면 조용히 틀린다.**
 *
 * 단위 오류는 예외를 내지 않는다. 숫자는 멀쩡해 보이고 뜻만 바뀐다. 백엔드는
 * `tests/unit/test_units.py` 가 지키고, 화면 쪽은 여기서 지킨다.
 */

import { describe, expect, it } from 'vitest'

import { DIMENSIONS, SI_BY_DIMENSION, UNITS_BY_DIMENSION, axisLabel, conditionUnits, display, formatScalar, formatValue, fromDisplay, spanToDisplay, toDisplay } from '@/shared/units'

describe('저장 단위와 표시 단위', () => {
  it('저장은 SI, 표시는 실무 단위', () => {
    expect(display('m')).toEqual({ unit: 'mm', factor: 1000, offset: 0 })
    expect(display('Pa')).toEqual({ unit: 'MPa', factor: 1e-6, offset: 0 })
    expect(toDisplay(0.05, 'm')).toBeCloseTo(50)
  })

  it('모르는 단위는 그대로 둔다', () => {
    // 지어내면 값이 틀린다. 바꾸지 않는 편이 낫다.
    expect(display('rad/s')).toEqual({ unit: 'rad/s', factor: 1, offset: 0 })
  })
})

describe('변형률과 tan δ', () => {
  it('변형률은 무차원으로 보여 준다', () => {
    // **v1.88.0 에 `%` 에서 옮겼다.** 이 시스템이 값을 넘겨 주는 곳은 솔버
    // 입력이고 거기서는 0.02 다. 화면과 덱이 다른 숫자를 보이면 옮겨 적을 때
    // 100배가 난다.
    expect(display('1', 'strain')).toEqual({ unit: '', factor: 1, offset: 0 })
    expect(toDisplay(0.02, '1', 'strain')).toBeCloseTo(0.02)
  })

  it('tan δ 도 비율 그대로다', () => {
    expect(display('1', 'dimensionless')).toEqual({ unit: '', factor: 1, offset: 0 })
    expect(toDisplay(0.02, '1', 'dimensionless')).toBeCloseTo(0.02)
  })

  it('변형률은 표에 **적혀 있어서** 무차원이다', () => {
    // 대충 넘어가서 무차원인 것과 다르다. `BY_SI['1']` 을 누가 바꾸면 변형률도
    // 따라 움직이는데, 그건 두 결정이 하나로 묶인 것이다 — 항목을 명시해 두면
    // 그때 여기가 깨진다.
    expect(display('1', 'strain')).not.toBe(display('1'))
    expect(display('1', 'strain')).toEqual(display('1'))
  })

  it('축 라벨에도 반영된다', () => {
    expect(axisLabel('변형률', '1', 'strain')).toBe('변형률')
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
    expect(conditionUnits(fields)).toEqual({ speed: 'mm/min', temperature: '°C' })
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

describe('처리 입력 칸의 단위', () => {
  it('길이는 mm, 면적은 mm² 로 받는다', () => {
    // CAE 는 길이를 mm 로 쓴다. `0.05` 를 치라고 하면 사람이 `50` 을 치고,
    // 그러면 **1000배** 틀린 곡선이 조용히 나온다.
    expect(display('m')).toEqual({ unit: 'mm', factor: 1000, offset: 0 })
    expect(display('m2')).toEqual({ unit: 'mm²', factor: 1e6, offset: 0 })
  })

  it('탄성 구간과 오프셋도 무차원으로 받는다', () => {
    // 규격은 "0.2% 오프셋" 이라고 적지만, 칸에 적는 것도 덱에 나가는 것도
    // 0.002 다. 화면이 둘 사이에서 100 을 곱했다 나눴다 하지 않는다.
    expect(display('1', 'strain')).toEqual({ unit: '', factor: 1, offset: 0 })
    expect(display('1')).toEqual({ unit: '', factor: 1, offset: 0 })
  })

  it('50 mm 는 0.05 m 로, 0.002 는 0.002 로 되돌아간다', () => {
    const length = display('m')
    expect(50 / length.factor).toBeCloseTo(0.05, 12)
    const strain = display('1', 'strain')
    expect(0.002 / strain.factor).toBeCloseTo(0.002, 12)
  })
})

describe('온도 — 원점이 다른 유일한 단위', () => {
  it('저장은 K, 화면은 °C', () => {
    // 오프셋이 없던 동안 DMA 곡선의 온도축이 `298 K` 로 나왔다. 실무에서
    // 그렇게 읽는 사람은 없다.
    expect(display('K')).toEqual({ unit: '°C', factor: 1, offset: -273.15 })
    expect(toDisplay(298.15, 'K')).toBeCloseTo(25, 10)
    expect(formatValue(298.15, null, 'K')).toBe('25 °C')
  })

  it('되돌리면 제자리다', () => {
    // 나누기만 하면 25 °C 가 25 K(-248 °C)로 간다. 짝을 맞춰 둔 이유다.
    expect(fromDisplay(25, 'K')).toBeCloseTo(298.15, 10)
    expect(fromDisplay(toDisplay(310.5, 'K'), 'K')).toBeCloseTo(310.5, 10)
  })

  it('차이(Δ)에는 오프셋을 쓰지 않는다', () => {
    // 온도 차 10 K 는 10 °C 이지 -263 °C 가 아니다. 65도 같은 구분을 갖고
    // 있었다 — `temperature.difference` 면 오프셋을 건너뛴다.
    expect(spanToDisplay(10, 'K')).toBe(10)
    expect(toDisplay(10, 'K')).toBeCloseTo(-263.15, 10)
  })

  it('곡선 축도 °C 로 적힌다', () => {
    // 축 라벨은 `display` 를 그대로 쓴다 — 여기가 맞으면 차트도 맞다.
    expect(axisLabel('온도', 'K', 'temperature')).toBe('온도 (°C)')
    expect(axisLabel('변위', 'm')).toBe('변위 (mm)')
  })

  it('오프셋이 없는 단위는 예전과 같다', () => {
    expect(toDisplay(0.05, 'm')).toBeCloseTo(50, 10)
    expect(fromDisplay(50, 'm')).toBeCloseTo(0.05, 10)
    expect(spanToDisplay(0.05, 'm')).toBeCloseTo(50, 10)
  })
})

describe('스칼라 표시 — 환산이 한 곳에만 있어야 한다', () => {
  it('응력은 크기에 따라 MPa·GPa 를 오간다', () => {
    // 205000 MPa 로 적힌 탄성계수는 아무도 안 읽는다.
    expect(formatScalar(205e9, 'Pa')).toBe('205 GPa')
    expect(formatScalar(252e6, 'Pa')).toBe('252 MPa')
  })

  it('Pa 말고도 안다', () => {
    // 복제돼 있던 세 벌은 전부 Pa 만 알아서, 스칼라가 m·K 로 오면 SI 그대로
    // 나왔다 — 0.05 m, 298.15 K.
    expect(formatScalar(0.05, 'm')).toBe('50 mm')
    expect(formatScalar(298.15, 'K')).toBe('25 °C')
    expect(formatScalar(1.212e-5, 'm2')).toBe('12.12 mm²')
  })

  it('변형률도 개수도 그대로 적는다', () => {
    expect(formatScalar(0.0686479, '1', 'strain')).toBe('0.068648')
    expect(formatScalar(14, '1')).toBe('14')
  })

  it('밀도는 CAE 단위로 적는다', () => {
    // 저장은 SI(kg/m³)다. 화면만 옮긴다 — 이 값을 그대로 덱에 적는 사람들의
    // 단위이고, 손으로 1e-12 를 곱하던 것이 사고의 자리였다.
    expect(formatValue(7850, null, 'kg/m3')).toBe('7.850e-9 tonne/mm³')
    expect(fromDisplay(toDisplay(7850, 'kg/m3'), 'kg/m3')).toBeCloseTo(7850, 6)
  })
})
