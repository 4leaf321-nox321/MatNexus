/**
 * 화살표로 줄 사이를 오간다 — **무는 것은 넷.**
 *
 *     Tab 순서에 줄 하나만 남는다   200줄이면 Tab 을 200번 눌러야 한다
 *     ↑↓ 로 앞뒤 줄로 옮긴다        옮기지 못하면 이 훅은 아무것도 아니다
 *     글자 치는 중엔 손대지 않는다   줄 안에 입력 칸이 있는 표가 있다
 *     Enter 가 그 줄을 연다         못 열면 화살표로 온 뒤 마우스를 다시 잡는다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { useRowFocus } from '@/shared/hooks/useRowFocus'

function Table({
  ids,
  onOpen,
  preferred,
  onMove,
}: {
  ids: string[]
  onOpen?: (id: string) => void
  preferred?: string
  onMove?: (id: string) => void
}) {
  const focus = useRowFocus(ids, { preferred, onMove })
  return (
    <table>
      <tbody>
        {ids.map((id) => (
          <tr key={id} {...focus.rowProps(id)} aria-label={`줄 ${id}`}>
            <td>
              <a
                href={`/x/${id}`}
                onClick={(event) => {
                  event.preventDefault()
                  onOpen?.(id)
                }}
              >
                {id}
              </a>
            </td>
            <td>
              <input aria-label={`메모 ${id}`} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function rowOf(id: string): HTMLElement {
  return screen.getByRole('row', { name: `줄 ${id}` })
}

describe('useRowFocus', () => {
  it('Tab 순서에는 줄 하나만 있다', () => {
    render(<Table ids={['a', 'b', 'c']} />)
    expect(rowOf('a')).toHaveAttribute('tabindex', '0')
    expect(rowOf('b')).toHaveAttribute('tabindex', '-1')
  })

  it('아래위 화살표가 앞뒤 줄로 옮긴다', async () => {
    const user = userEvent.setup()
    render(<Table ids={['a', 'b', 'c']} />)
    rowOf('a').focus()

    await user.keyboard('{ArrowDown}')
    expect(rowOf('b')).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(rowOf('c')).toHaveFocus()
    await user.keyboard('{ArrowUp}')
    expect(rowOf('b')).toHaveFocus()
  })

  it('끝에서는 멈춘다', async () => {
    // **감아 돌지 않는다.** 마지막에서 한 번 더 눌러 첫 줄로 튀면, 사람은
    // 목록을 다 봤다는 것을 모른 채 같은 줄을 다시 훑는다.
    const user = userEvent.setup()
    render(<Table ids={['a', 'b']} />)
    rowOf('b').focus()
    await user.keyboard('{ArrowDown}')
    expect(rowOf('b')).toHaveFocus()
  })

  it('Home 과 End 가 처음과 끝으로 간다', async () => {
    const user = userEvent.setup()
    render(<Table ids={['a', 'b', 'c']} />)
    rowOf('b').focus()
    await user.keyboard('{End}')
    expect(rowOf('c')).toHaveFocus()
    await user.keyboard('{Home}')
    expect(rowOf('a')).toHaveFocus()
  })

  it('옮겨 간 줄이 Tab 순서를 물려받는다', async () => {
    const user = userEvent.setup()
    render(<Table ids={['a', 'b']} />)
    rowOf('a').focus()
    await user.keyboard('{ArrowDown}')
    expect(rowOf('b')).toHaveAttribute('tabindex', '0')
    expect(rowOf('a')).toHaveAttribute('tabindex', '-1')
  })

  it('입력 칸 안에서는 화살표를 가로채지 않는다', async () => {
    const user = userEvent.setup()
    render(<Table ids={['a', 'b']} />)
    const memo = screen.getByLabelText('메모 a')
    await user.click(memo)
    await user.keyboard('{ArrowDown}')
    expect(memo).toHaveFocus()
  })

  it('누른 줄이 곧 지금 줄이다', async () => {
    // 클릭하고 화살표를 눌렀는데 포커스가 표 밖이면 그 화살표는 **페이지를
    // 스크롤한다** — 「화살표가 스크롤부터 한다」 로 보인다(2026-09-11 지적).
    const user = userEvent.setup()
    render(<Table ids={['a', 'b', 'c']} />)
    await user.click(rowOf('b'))
    expect(rowOf('b')).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(rowOf('c')).toHaveFocus()
  })

  it('링크를 누른 것은 줄을 누른 것이 아니다', async () => {
    // 링크·단추를 누르면 그쪽이 포커스를 가져야 한다 — 뺏으면 클릭이 안 먹거나
    // 두 번 눌러야 하는 것처럼 보인다.
    const user = userEvent.setup()
    render(<Table ids={['a', 'b']} onOpen={() => {}} />)
    await user.click(screen.getByRole('link', { name: 'b' }))
    expect(rowOf('b')).not.toHaveFocus()
  })

  it('옮기면 곧 고른 것이 된다', async () => {
    // 「이동 후 엔터를 눌러야 선택된다」 — 목록 안에서 고르는 일이 끝나는
    // 화면(재료 상세의 왼쪽 목록)에서는 옮기는 것이 곧 고르는 것이다
    // (2026-09-11 지적).
    const user = userEvent.setup()
    const onMove = vi.fn()
    render(<Table ids={['a', 'b', 'c']} onMove={onMove} />)
    rowOf('a').focus()

    await user.keyboard('{ArrowDown}')
    expect(onMove).toHaveBeenCalledWith('b')
    await user.keyboard('{End}')
    expect(onMove).toHaveBeenLastCalledWith('c')
  })

  it('마우스로 누른 것과 Tab 으로 들어온 것에는 안 부른다', async () => {
    // 클릭은 사람이 이미 「거기로 간다」 를 뜻한 것이고(링크가 제 일을 한다),
    // Tab 은 아직 아무것도 안 고른 것이다.
    const user = userEvent.setup()
    const onMove = vi.fn()
    render(<Table ids={['a', 'b']} onMove={onMove} />)
    await user.click(rowOf('b'))
    await user.tab()
    expect(onMove).not.toHaveBeenCalled()
  })

  it('끝에서 더 눌러도 다시 고르지 않는다', async () => {
    // 못 옮겼으면 안 부른다 — 같은 줄을 거듭 고르면 그때마다 다시 읽는다.
    const user = userEvent.setup()
    const onMove = vi.fn()
    render(<Table ids={['a', 'b']} onMove={onMove} />)
    rowOf('b').focus()
    await user.keyboard('{ArrowDown}')
    expect(onMove).not.toHaveBeenCalled()
  })

  it('Enter 가 그 줄의 링크를 연다', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    render(<Table ids={['a', 'b']} onOpen={onOpen} />)
    rowOf('b').focus()
    await user.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledWith('b')
  })

  it('짚어 준 줄이 Tab 순서를 든다', () => {
    // 「지금 보고 있는 것」 이 있는 목록(재료 상세 왼쪽)에서 첫 줄로 두면,
    // 50번째 재료를 보는 중에도 Tab 이 처음으로 간다(2026-09-11 지적).
    render(<Table ids={['a', 'b', 'c']} preferred="c" />)
    expect(rowOf('c')).toHaveAttribute('tabindex', '0')
    expect(rowOf('a')).toHaveAttribute('tabindex', '-1')
  })

  it('짚어 준 줄이 걸러져 사라지면 첫 줄로 돌아간다', () => {
    render(<Table ids={['a', 'b']} preferred="zz" />)
    expect(rowOf('a')).toHaveAttribute('tabindex', '0')
  })

  it('줄이 걸러져 사라져도 Tab 으로 들어갈 수 있다', () => {
    // 아무 줄도 `0` 이 아니면 **표에 Tab 으로 아예 못 들어간다.**
    const { rerender } = render(<Table ids={['a', 'b']} />)
    rowOf('a').focus()
    rerender(<Table ids={['c', 'd']} />)
    expect(rowOf('c')).toHaveAttribute('tabindex', '0')
  })
})
