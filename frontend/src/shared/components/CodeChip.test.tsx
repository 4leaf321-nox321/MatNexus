/**
 * 고유 번호 칩 — **보이고, 누르면 복사된다**(ADR 0043).
 *
 * 링크 · 펼침 줄 안에 서므로 누른 것이 그쪽으로 새면 안 된다 — 번호를 복사하려다 다른 화면으로
 * 넘어가면 다시는 안 누른다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CodeChip } from '@/shared/components/CodeChip'

/**
 * **복사는 `copyText` 를 거친다**(2026-10-04). `navigator.clipboard` 를 바로 부르면 사내 http
 * 주소에서는 그 객체가 없어 아무 일도 안 일어났다. 두 길(비동기 API · 숨은 칸)은 그 함수의 일이다.
 */
const copyText = vi.fn()
vi.mock('@/shared/lib/clipboard', () => ({
  copyText: (text: string) => copyText(text),
}))

beforeEach(() => {
  copyText.mockReset()
  copyText.mockResolvedValue(true)
})

describe('CodeChip', () => {
  it('누르면 번호를 복사하고, 누른 것이 바깥으로 새지 않는다', async () => {
    const user = userEvent.setup()
    const outside = vi.fn()
    render(
      <div onClick={outside}>
        <CodeChip code="T-000203" />
      </div>
    )

    const chip = screen.getByRole('button', { name: '번호 T-000203 복사' })
    expect(chip).toHaveTextContent('T-000203')
    await user.click(chip)

    expect(copyText).toHaveBeenCalledWith('T-000203')
    await waitFor(() => expect(chip).toHaveAttribute('title', '복사했습니다'))
    expect(outside).not.toHaveBeenCalled()
  })

  it('복사가 막히면 「복사했습니다」 를 띄우지 않는다', async () => {
    // 막혔는데 됐다고 하면 사람은 빈 칸을 붙여 넣는다.
    copyText.mockResolvedValue(false)
    const user = userEvent.setup()
    render(<CodeChip code="T-000203" />)
    const chip = screen.getByRole('button', { name: '번호 T-000203 복사' })
    await user.click(chip)

    await waitFor(() => expect(copyText).toHaveBeenCalledWith('T-000203'))
    // 답이 돌아온 뒤에 본다 — 한 틱 기다린다.
    await Promise.resolve()
    expect(chip).not.toHaveAttribute('title', '복사했습니다')
  })

  it('번호가 없으면 아무것도 안 그린다', () => {
    const { container } = render(<CodeChip code={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
