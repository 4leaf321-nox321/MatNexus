/**
 * 고유 번호 칩 — **보이고, 누르면 복사된다**(ADR 0043).
 *
 * 링크 · 펼침 줄 안에 서므로 누른 것이 그쪽으로 새면 안 된다 — 번호를 복사하려다 다른 화면으로
 * 넘어가면 다시는 안 누른다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CodeChip } from '@/shared/components/CodeChip'

describe('CodeChip', () => {
  it('누르면 번호를 복사하고, 누른 것이 바깥으로 새지 않는다', async () => {
    const user = userEvent.setup()
    // userEvent.setup 이 클립보드를 흉내 낸다 — 그 뒤에 감시를 건다.
    const written = vi.spyOn(navigator.clipboard, 'writeText')
    const outside = vi.fn()
    render(
      <div onClick={outside}>
        <CodeChip code="T-000203" />
      </div>
    )

    const chip = screen.getByRole('button', { name: '번호 T-000203 복사' })
    expect(chip).toHaveTextContent('T-000203')
    await user.click(chip)

    expect(written).toHaveBeenCalledWith('T-000203')
    await waitFor(() => expect(chip).toHaveAttribute('title', '복사했습니다'))
    expect(outside).not.toHaveBeenCalled()
  })

  it('번호가 없으면 아무것도 안 그린다', () => {
    const { container } = render(<CodeChip code={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
