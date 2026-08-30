/**
 * 요건 표. **화면 셋이 같은 규칙을 봐야 한다** — 시험 상세의 점탄성 탭, 겹치기,
 * 가져오기.
 *
 * 규칙이 화면마다 흩어져 있으면 한쪽만 고쳐진 채 「정의 화면은 열린다는데 안
 * 뜬다」 가 된다. 그래서 표를 한 곳에 두고, 그 표가 실제 조건과 맞는지 여기서 왼다.
 */

import { describe, expect, it } from 'vitest'

import { CAPABILITIES, hasViscoelasticTab, missingFor } from '@/modules/tests/capabilities'

function capability(id: string) {
  const found = CAPABILITIES.find((one) => one.id === id)
  if (!found) throw new Error(`${id} 가 없습니다`)
  return found
}

describe('점탄성 탭', () => {
  it('저장·손실 탄성률이 둘 다 있어야 열린다', () => {
    expect(hasViscoelasticTab(['storage_modulus', 'loss_modulus'])).toBe(true)
  })

  it('하나만 있으면 안 열린다', () => {
    // **이것이 시험 상세 화면의 실제 조건이다.** 느슨하게 하면 인장 시험에도
    // 탭이 떠서, 눌러 보고서야 아무것도 없다는 것을 안다.
    expect(hasViscoelasticTab(['storage_modulus'])).toBe(false)
    expect(hasViscoelasticTab(['loss_modulus'])).toBe(false)
  })

  it('인장 채널로는 안 열린다', () => {
    expect(hasViscoelasticTab(['force', 'displacement', 'stress', 'strain'])).toBe(false)
  })
})

describe('무엇이 빠졌는지', () => {
  it('빠진 것을 이름으로 돌려준다', () => {
    expect(missingFor(capability('viscoelastic_tab'), ['storage_modulus'])).toEqual([
      ['loss_modulus'],
    ])
  })

  it('여럿 중 하나면 채워진 것으로 본다', () => {
    // **각주파수만 있는 표가 실재한다** — 실측 파일의 첫 스윕에만 `Frequency`
    // 열이 있고 나머지 여섯에는 없었다. 그것을 못 채웠다고 적으면 거짓말이다.
    expect(
      missingFor(capability('master_curve'), [
        'temperature',
        'storage_modulus',
        'angular_frequency',
      ])
    ).toEqual([])
  })

  it('가져오기는 장비마다 다른 이름을 받아 준다', () => {
    expect(missingFor(capability('master_curve_import'), ['omega', 'e_prime'])).toEqual([])
  })
})

describe('무엇을 보는가', () => {
  it('셋이 서로 다른 목록을 본다', () => {
    // **이 차이가 「탭은 떴는데 겹칠 스윕이 없습니다」 의 정체다.** 하나로
    // 합치면 그 조합을 화면이 설명할 수 없다.
    expect(capability('viscoelastic_tab').scope).toBe('type')
    expect(capability('master_curve').scope).toBe('measured')
    expect(capability('master_curve_import').scope).toBe('derived')
  })
})
