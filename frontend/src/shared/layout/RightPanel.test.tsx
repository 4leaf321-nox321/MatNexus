/**
 * 오른쪽 영역 — **자리는 껍데기가, 내용은 화면이, 여닫기는 상단 바가.**
 *
 * 여기서 지키는 것 셋.
 *
 *   1. 아무도 안 쓰면 **없는 것과 같다.** 빈 자리가 폭을 먹으면 모든 화면이
 *      그만큼 좁아진다.
 *   2. 화면이 사라지면 **내용도 등록도 같이 걷힌다.** 탭을 옮겼는데 앞 화면의
 *      사이드바가 남아 있거나, 없는 패널을 여는 단추가 상단 바에 남아 있으면
 *      눌러도 아무 일이 안 일어난다.
 *   3. **여는 단추는 상단 바에 있다.** 처음에는 화면 오른쪽 끝의 흐린 세로
 *      띠였는데 아무도 못 봤다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import {
  RightPanel,
  RightPanelHost,
  RightPanelProvider,
  useRightPanel,
} from '@/shared/layout/RightPanel'

/** 상단 바 몫 — 패널이 등록됐을 때만 단추를 낸다. */
function FakeHeader() {
  const { label, open, toggle } = useRightPanel()
  if (!label) return null
  return (
    <button type="button" onClick={toggle} aria-pressed={open}>
      {label} {open ? '접기' : '펴기'}
    </button>
  )
}

function Shell({ children }: { children?: React.ReactNode }) {
  return (
    <RightPanelProvider>
      <div>
        <FakeHeader />
        <main data-testid="main">본문</main>
        <RightPanelHost />
        {children}
      </div>
    </RightPanelProvider>
  )
}

const panel = (
  <RightPanel label="변수 목록">
    <aside>이름의 뜻</aside>
  </RightPanel>
)

describe('오른쪽 영역', () => {
  it('아무도 안 쓰면 비어 있고 단추도 없다', () => {
    const { container } = render(<Shell />)
    expect(container.querySelector('#app-right-panel')?.childElementCount).toBe(0)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('화면이 등록하면 상단 바에 여는 단추가 뜬다 — 기본은 닫힘', () => {
    render(<Shell>{panel}</Shell>)
    expect(screen.getByRole('button', { name: '변수 목록 펴기' })).toBeInTheDocument()
    // 늘 펴 두면 본문이 그만큼 좁아진다.
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('열면 본문이 아니라 그 자리에 붙는다', async () => {
    const user = userEvent.setup()
    render(<Shell>{panel}</Shell>)
    await user.click(screen.getByRole('button', { name: '변수 목록 펴기' }))

    const host = document.getElementById('app-right-panel')
    // 본문 안이면 `mx-auto max-w-7xl` 을 따라 가운데로 딸려 들어간다.
    expect(host).toContainElement(screen.getByRole('complementary'))
    expect(screen.getByTestId('main')).not.toContainElement(screen.getByRole('complementary'))
  })

  it('넣은 화면이 사라지면 내용도 단추도 같이 걷힌다', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<Shell>{panel}</Shell>)
    await user.click(screen.getByRole('button', { name: '변수 목록 펴기' }))
    expect(screen.getByRole('complementary')).toBeInTheDocument()

    rerender(<Shell />)
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(document.getElementById('app-right-panel')?.childElementCount).toBe(0)
  })
})
