/**
 * 「뒤로」 가 왔던 자리로 가는가.
 *
 * 전에는 무조건 재료 화면이었다. 목록에서 20건을 훑던 사람은 돌아올 때마다
 * **자리를 잃었다** — 다시 목록을 찾아 들어가야 했다.
 */

import { describe, expect, it } from 'vitest'

import { backTarget, materialTarget } from '@/modules/tests/backTarget'

const MATERIAL = { material_id: 'm1', material_name: 'SECC_MDOI_1.0' }

describe('시험 상세의 뒤로', () => {
  it('목록에서 왔으면 목록으로 간다', () => {
    // 시험 목록은 부서 스코프라 상세 화면이 그 주소를 만들 수 없다 — 목록이 준다.
    const from = { to: '/w/qa/tests', label: '시험 데이터' }
    expect(backTarget(from, MATERIAL)).toEqual(from)
  })

  it('넘겨받은 것이 없으면 그 재료로 간다', () => {
    // 주소를 직접 쳤거나 재료에서 들어온 경우. 재료 상세가 그 시험의 시편·형제
    // 시험을 함께 갖고 있는 화면이다.
    expect(backTarget(undefined, MATERIAL)).toEqual({
      to: '/materials/m1',
      label: 'SECC_MDOI_1.0',
    })
  })

  it('재료를 모르면 카탈로그로 간다', () => {
    // **막다른 곳을 만들지 않는다.** 전사 화면이라 언제나 갈 수 있다.
    expect(backTarget(undefined, null)).toEqual({ to: '/materials', label: '재료 목록' })
    expect(backTarget(undefined, { material_id: null })).toEqual({
      to: '/materials',
      label: '재료 목록',
    })
  })

  it('재료 이름이 없어도 라벨이 빈 채로 안 나간다', () => {
    // 라벨이 비면 화살표만 남아서 어디로 가는지 알 수 없다.
    expect(backTarget(undefined, { material_id: 'm1', material_name: null }).label).toBe('재료')
  })
})

describe('materialTarget', () => {
  it('왔던 자리와 무관하게 재료로 간다', () => {
    // **`backTarget` 과 갈리는 지점이다.** 목록에서 들어오면 「뒤로」 는 목록으로
    // 가고, 그때 재료로 갈 길은 이것뿐이다.
    expect(materialTarget({ material_id: 'm1', material_name: 'DP600' })).toEqual({
      to: '/materials/m1',
      label: 'DP600',
    })
  })

  it('재료를 모르면 길이 없다', () => {
    expect(materialTarget({ material_id: null, material_name: 'DP600' })).toBeNull()
    expect(materialTarget(null)).toBeNull()
  })

  it('이름이 없어도 갈 수는 있다', () => {
    expect(materialTarget({ material_id: 'm1', material_name: null })?.label).toBe('재료')
  })
})
