/**
 * 탭 이름은 주소에 실린다 — **모르는 값에 빈 화면을 보이지 않는다.**
 */

import { describe, expect, it } from 'vitest'

import { tabOf } from '@/modules/materials/tabs'

describe('주소가 지목한 탭', () => {
  it('아는 이름은 그대로 연다', () => {
    // 워크벤치가 「그 재료의 CAE 카드로」 로 보낼 때 쓰는 이름이다.
    expect(tabOf('cards')).toBe('cards')
    expect(tabOf('properties')).toBe('properties')
  })

  it('모르는 이름·빈 값은 첫 탭으로 돌린다', () => {
    // 탭 이름을 바꾼 뒤 옛 링크나 즐겨찾기가 남아 있을 수 있다.
    expect(tabOf('없어진탭')).toBe('samples')
    expect(tabOf(null)).toBe('samples')
    expect(tabOf(undefined)).toBe('samples')
  })
})
