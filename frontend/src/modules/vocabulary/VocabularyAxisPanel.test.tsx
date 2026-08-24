/**
 * 기준정보 축 목록 옆패널.
 *
 * 전에는 본문 위의 가로 버튼 줄이었다. 축이 열한 개라 줄이 넘치고, **부모-자식이
 * 안 보였다** — Grade 는 Category 아래, Category 는 Family 아래인데 나란히
 * 놓으면 그냥 열한 개다.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   계층을 들여쓰기로 그린다   나란히 놓으면 종속 관계가 사라진다
 *   지금 축을 짚는다          어디 있는지 모르면 목록이 아니라 나열이다
 *   개수를 함께 보인다        비어 있는 축을 눌러 보고 나서 알면 늦다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { VocabularyAxisPanel } from '@/modules/vocabulary/VocabularyAxisPanel'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

function axis(slug: string, label: string, parent: string | null, count = 0) {
  return {
    slug,
    label,
    parent_slug: parent,
    entry_policy: 'open',
    term_count: count,
    attribute_source: null,
  }
}

/** 실제 축들. Grade 는 Category 아래, Category 는 Family 아래다. */
const AXES = [
  axis('family', 'Family', null, 3),
  axis('category', 'Category', 'family', 5),
  axis('grade', 'Grade', 'category', 94),
  axis('manufacturer', '제조사', null, 12),
]

function panel(current: string | null = null, onPick = vi.fn()) {
  render(
    <LeftPanelProvider>
      <LeftPanelHost />
      <VocabularyAxisPanel axes={AXES} current={current} onPick={onPick} />
    </LeftPanelProvider>
  )
  return onPick
}

function indent(name: string): number {
  const button = screen.getByRole('button', { name: new RegExp(name) })
  return Number.parseFloat(button.style.paddingLeft)
}

describe('기준정보 축 목록', () => {
  it('계층을 들여쓰기로 그린다', () => {
    // **나란히 놓으면 종속 관계가 사라진다.** Grade 가 Category 아래라는 것이
    // 화면에 남아야 한다.
    panel()
    expect(indent('Family')).toBeLessThan(indent('Category'))
    expect(indent('Category')).toBeLessThan(indent('Grade'))
    // 부모가 없는 축은 Family 와 같은 단이다.
    expect(indent('제조사')).toBe(indent('Family'))
  })

  it('지금 보고 있는 축을 짚는다', () => {
    panel('grade')
    expect(screen.getByRole('button', { name: /Grade/ })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /Family/ })).not.toHaveAttribute('aria-current')
  })

  it('누르면 그 축으로 바꾼다', async () => {
    const onPick = panel('family')
    await userEvent.click(screen.getByRole('button', { name: /제조사/ }))
    expect(onPick).toHaveBeenCalledWith('manufacturer')
  })

  it('값 개수를 함께 보인다', () => {
    // 비어 있는 축을 눌러 보고 나서 아는 것보다 미리 아는 것이 낫다.
    panel()
    expect(screen.getByRole('button', { name: /Grade/ })).toHaveTextContent('94')
  })

  it('축이 강종이 아니라 Grade 다', () => {
    // 강종(鋼種)은 강(鋼)에만 쓰는 말인데 이 축은 재료군을 안 가린다 —
    // 개발 DB 에 Polymer/PP 의 Grade 가 있다. 재료 화면은 처음부터 "Grade" 로
    // 부르고 있었고, 기준정보만 다른 이름을 쓰고 있었다.
    panel()
    expect(screen.getByRole('button', { name: /Grade/ })).toBeInTheDocument()
    expect(screen.queryByText('강종')).not.toBeInTheDocument()
  })
})
