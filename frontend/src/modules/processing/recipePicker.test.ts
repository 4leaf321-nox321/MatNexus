/**
 * 레시피 검색 — **이름만으로는 못 찾는다.**
 *
 * 사람이 기억하는 방식은 "네킹 자르는 그거", "TD 부서 표준", "0.2% 짜리" 다.
 * 이름만 훑으면 그 어느 것도 안 걸린다. 그래서 부서·시험종류·단계 이름까지
 * 함께 본다.
 *
 * 드롭다운으로 두면 안 되는 이유가 이것이다 — 스무 개가 넘어가면 이름을 눈으로
 * 훑는 방식 자체가 안 통한다.
 */

import { describe, expect, it } from 'vitest'

import { matches } from '@/modules/processing/RecipePicker'
import type { Recipe } from '@/modules/processing/api'

const recipe = (over: Partial<Recipe> = {}): Recipe =>
  ({
    id: '00000000-0000-0000-0000-000000000000',
    key: 'tensile_standard',
    label: '인장 표준',
    description: null,
    owner_workspace_slug: 'td',
    owner_workspace_name: 'TD 사업부',
    is_global: false,
    test_type_key: 'tensile',
    test_type_label: '인장시험',
    steps: [
      { plugin: 'tensile.engineering', options: {} },
      { plugin: 'tensile.necking_candidate', options: {} },
    ],
    is_active: true,
    created_at: '2026-08-17T00:00:00Z',
    updated_at: '2026-08-17T00:00:00Z',
    ...over,
  }) as unknown as Recipe

describe('레시피 검색', () => {
  it('빈 검색어는 전부 통과시킨다', () => {
    expect(matches(recipe(), '')).toBe(true)
  })

  it('이름·키로 찾는다', () => {
    expect(matches(recipe(), '인장')).toBe(true)
    expect(matches(recipe(), 'standard')).toBe(true)
  })

  it('부서로 찾는다', () => {
    // "TD 부서 표준" 이 사람이 기억하는 방식이다.
    expect(matches(recipe(), 'TD')).toBe(true)
    expect(matches(recipe({ is_global: true, owner_workspace_name: null }), '전역')).toBe(true)
  })

  it('단계 이름으로 찾는다', () => {
    // "네킹 자르는 그거" — 이름에는 네킹이 없어도 단계에는 있다.
    expect(matches(recipe(), 'necking')).toBe(true)
  })

  it('여러 낱말은 전부 걸려야 한다', () => {
    // 좁히려고 낱말을 더했는데 결과가 늘면 검색이 아니다.
    expect(matches(recipe(), '인장 TD')).toBe(true)
    expect(matches(recipe(), '인장 없는부서')).toBe(false)
  })

  it('대소문자를 가리지 않는다', () => {
    expect(matches(recipe(), 'NECKING')).toBe(true)
    expect(matches(recipe(), 'td')).toBe(true)
  })
})
