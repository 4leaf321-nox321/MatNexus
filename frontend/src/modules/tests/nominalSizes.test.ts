import { describe, expect, it } from 'vitest'

import { nominalSizes } from '@/modules/tests/nominalSizes'
import type { SpecimenField } from '@/modules/vocabulary/api'

function field(key: string, siUnit = 'm', dimension = 'length'): SpecimenField {
  return {
    key,
    label: key,
    kind: 'number',
    dimension,
    si_unit: siUnit,
    choices: [],
    inherited: true,
    is_required: false,
  }
}

const FIELDS = [field('thickness'), field('width'), field('gauge_length')]

describe('nominalSizes', () => {
  it('저장 단위에서 화면 단위로 바꾼다', () => {
    // **여기가 이 파일의 전부다.** 0.05 를 그대로 보여 주면 사람은 게이지가
    // 0.05 mm 인 줄 안다.
    expect(nominalSizes({ gauge_length: 0.05, width: 0.0125 }, FIELDS)).toEqual({
      gauge: '50',
      width: '12.5',
    })
  })

  it('게이지는 규격 쪽 이름이 다르다', () => {
    expect(nominalSizes({ gauge_length: 0.025 }, FIELDS).gauge).toBe('25')
  })

  it('규격에 없는 칸은 빠진다', () => {
    expect(nominalSizes({ gauge_length: 0.05 }, FIELDS)).not.toHaveProperty('thickness')
  })

  it('칸을 못 찾으면 버린다 — 단위를 모르는 숫자는 안 보여 준다', () => {
    expect(nominalSizes({ gauge_length: 0.05 }, [])).toEqual({})
  })

  it('숫자가 아닌 값은 버린다', () => {
    expect(nominalSizes({ thickness: '얇게' }, FIELDS)).toEqual({})
  })

  it('부동소수 꼬리를 남기지 않는다', () => {
    // 0.0025 * 1000 은 2.5000000000000004 로 떨어진다.
    expect(nominalSizes({ thickness: 0.0025 }, FIELDS).thickness).toBe('2.5')
  })
})
