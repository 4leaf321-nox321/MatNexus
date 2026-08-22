/**
 * 축의 역할 — **화면에 축 이름을 박지 않는다.**
 *
 * 어느 축이 치수를 갖고 어느 축이 기본 칸을 갖는지는 축 목록만 보면 안다.
 * `slug === 'specimen_standard'` 를 화면에 적으면 축이 하나 더 생길 때 두 곳을
 * 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
 */

import { describe, expect, it } from 'vitest'

import { roleOf } from '@/modules/vocabulary/VocabularyAdminPage'
import type { Vocabulary } from '@/modules/vocabulary/api'

const axis = (over: Partial<Vocabulary> & { slug: string }): Vocabulary =>
  ({
    label: over.slug,
    entry_policy: 'open',
    term_count: 0,
    parent_slug: null,
    attribute_source: null,
    ...over,
  }) as Vocabulary

const CATEGORY = axis({ slug: 'specimen_category' })
const STANDARD = axis({
  slug: 'specimen_standard',
  parent_slug: 'specimen_category',
  attribute_source: 'parent',
})
const PLAIN = axis({ slug: 'manufacturer' })
/** 부모가 있지만 치수와는 무관한 축. `grade` 의 부모는 `category` 다. */
const GRADE = axis({ slug: 'grade', parent_slug: 'category' })
const PLAIN_PARENT = axis({ slug: 'category' })

const ALL = [CATEGORY, STANDARD, PLAIN, GRADE, PLAIN_PARENT]

describe('축의 역할', () => {
  it('값이 치수를 갖는 축', () => {
    expect(roleOf(STANDARD, ALL)).toBe('standard')
  })

  it('값이 기본 칸을 갖는 축 — 위 축의 부모다', () => {
    expect(roleOf(CATEGORY, ALL)).toBe('category')
  })

  it('치수와 무관한 축은 아무 역할도 없다', () => {
    expect(roleOf(PLAIN, ALL)).toBeNull()
  })

  it('부모라고 다 분류가 아니다', () => {
    // `category` 는 `grade` 의 부모지만 `grade` 는 치수를 갖지 않는다.
    // 그것까지 분류로 보면 강종 화면에 자 버튼이 뜬다.
    expect(roleOf(PLAIN_PARENT, ALL)).toBeNull()
  })
})
