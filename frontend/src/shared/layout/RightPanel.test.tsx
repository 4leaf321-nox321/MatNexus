/**
 * 오른쪽 영역 — **자리는 껍데기가, 내용은 화면이.**
 *
 * 여기서 지키는 것 둘.
 *
 *   1. 아무도 안 쓰면 **없는 것과 같다.** 빈 자리가 폭을 먹으면 모든 화면이
 *      그만큼 좁아진다.
 *   2. 화면이 사라지면 **내용도 같이 걷힌다.** 탭을 옮겼는데 앞 화면의
 *      사이드바가 남아 있으면 그것을 치우는 코드를 따로 둬야 하고, 그런 코드는
 *      한 곳을 빠뜨린다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RightPanel, RightPanelHost } from '@/shared/layout/RightPanel'

function Shell({ children }: { children?: React.ReactNode }) {
  return (
    <div>
      <main data-testid="main">본문</main>
      <RightPanelHost />
      {children}
    </div>
  )
}

describe('오른쪽 영역', () => {
  it('아무도 안 쓰면 비어 있다', () => {
    const { container } = render(<Shell />)
    expect(container.querySelector('#app-right-panel')?.childElementCount).toBe(0)
  })

  it('화면이 넣은 것이 그 자리에 뜬다', () => {
    render(
      <Shell>
        <RightPanel>
          <aside>변수 목록</aside>
        </RightPanel>
      </Shell>
    )
    const host = document.getElementById('app-right-panel')
    // **본문 안이 아니라 그 자리**에 붙는다. 본문 안이면 `mx-auto max-w-7xl` 을
    // 따라 가운데로 딸려 들어간다.
    expect(host).toContainElement(screen.getByRole('complementary'))
    expect(screen.getByTestId('main')).not.toContainElement(screen.getByRole('complementary'))
  })

  it('넣은 화면이 사라지면 같이 걷힌다', () => {
    const { rerender } = render(
      <Shell>
        <RightPanel>
          <aside>변수 목록</aside>
        </RightPanel>
      </Shell>
    )
    expect(screen.getByRole('complementary')).toBeInTheDocument()

    rerender(<Shell />)
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(document.getElementById('app-right-panel')?.childElementCount).toBe(0)
  })
})
