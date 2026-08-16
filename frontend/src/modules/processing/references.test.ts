/**
 * 참조는 **칸마다 최대 하나**여야 한다.
 *
 * 처음에는 단위로 골랐다 — `param.unit === 'm'` 인 것을 전부 후보로 냈다.
 * 그랬더니 '게이지 길이' 칸에 게이지 길이·폭·두께 셋이 붙었고, 버튼 이름은 전부
 * '참조' 라 무엇을 누르는지 알 수 없었다. **셋이 똑같아 보이는데 결과는 다르다.**
 *
 * 잘못 누르면 게이지 길이(50mm) 자리에 두께(1mm)가 들어간다. 오류는 안 난다 —
 * 변형률이 50배 커진 그럴듯한 곡선이 나올 뿐이다. 이 프로젝트가 가장 비싸게 겪는
 * "조용히 틀린 성공" 계열이다.
 */

import { describe, expect, it } from 'vitest'

import { REFERENCE_FOR, isReference, referenceLabel } from '@/modules/processing/api'

describe('참조', () => {
  it('칸 하나에 후보가 하나뿐이다', () => {
    // 단위로 고르던 때는 'm' 인 칸에 셋이 붙었다. 이름으로 고르면 구조적으로
    // 하나다 — 이 검사는 그 구조가 유지되는지를 본다.
    for (const [name, item] of Object.entries(REFERENCE_FOR)) {
      expect(item.key, name).toBeTruthy()
      expect(item.label, name).toBeTruthy()
    }
  })

  it('게이지 길이에는 게이지 길이만 붙는다', () => {
    expect(REFERENCE_FOR.gauge_length.key).toBe('specimen_gauge_length')
    // 폭·두께는 단위가 같지만 뜻이 다르다. 후보로 나오면 안 된다.
    const keys = Object.values(REFERENCE_FOR).map((item) => item.key)
    expect(keys).not.toContain('specimen_width')
    expect(keys).not.toContain('specimen_thickness')
  })

  it('단면적은 면적을 가리킨다', () => {
    expect(REFERENCE_FOR.area.key).toBe('specimen_area')
  })

  it('원문 대신 사람이 읽는 이름을 보여 준다', () => {
    // `@specimen_gauge_length` 를 그대로 띄우면 이게 무엇인지 코드를 읽어야 안다.
    expect(referenceLabel('@specimen_gauge_length')).toBe('시편의 게이지 길이')
    expect(referenceLabel('@youngs_modulus')).toBe('앞 단계에서 잰 탄성계수')
  })

  it('모르는 참조는 원문을 그대로 보여 준다', () => {
    // 감추면 "빈 칸" 으로 읽힌다. 모르는 것은 모르는 대로 보여 주는 편이 낫다.
    expect(referenceLabel('@made_up')).toBe('made_up')
  })

  it('숫자는 참조가 아니다', () => {
    expect(isReference(0.05)).toBe(false)
    expect(isReference('0.05')).toBe(false)
    expect(isReference('@specimen_area')).toBe(true)
  })
})
