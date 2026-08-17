/**
 * 선택기 — **값이 많아져도 쓸 수 있는가.**
 *
 * 처음에는 값을 버튼으로 줄줄이 폈다. 둘일 때는 그게 제일 빠르지만 스무 개만
 * 넘어가도 줄이 무너진다. 여기서 지키는 것은 그 한계가 실제로 없어졌는지다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { OptionPicker } from '@/shared/components/OptionPicker'

function many(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    value: `Cat${String(i).padStart(3, '0')}`,
    count: i,
  }))
}

describe('OptionPicker', () => {
  it('고른 값이 열지 않아도 보인다', () => {
    render(<OptionPicker label="Family" value="Metal" options={[]} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Metal/ })).toBeInTheDocument()
  })

  it('안 고르면 전체라고 말한다', () => {
    render(<OptionPicker label="Family" value="" options={[]} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /전체/ })).toBeInTheDocument()
  })

  it('검색으로 좁힌다', async () => {
    const user = userEvent.setup()
    render(
      <OptionPicker
        label="Category"
        value=""
        options={[
          { value: 'Steel', count: 58 },
          { value: 'Aluminum', count: 3 },
          { value: 'Stainless', count: 1 },
        ]}
        onChange={vi.fn()}
      />
    )
    await user.click(screen.getByRole('button', { name: /전체/ }))
    await user.type(await screen.findByPlaceholderText('Category 찾기'), 'st')

    await waitFor(() => {
      expect(screen.getByText('Steel')).toBeInTheDocument()
      expect(screen.getByText('Stainless')).toBeInTheDocument()
      expect(screen.queryByText('Aluminum')).not.toBeInTheDocument()
    })
  })

  it('많이 쓰이는 것이 위로 온다', async () => {
    const user = userEvent.setup()
    render(
      <OptionPicker
        label="Category"
        value=""
        options={[
          { value: 'Rare', count: 1 },
          { value: 'Common', count: 99 },
        ]}
        onChange={vi.fn()}
      />
    )
    await user.click(screen.getByRole('button', { name: /전체/ }))
    const rows = await screen.findAllByRole('button')
    const labels = rows.map((row) => row.textContent ?? '')
    expect(labels.findIndex((t) => t.includes('Common'))).toBeLessThan(
      labels.findIndex((t) => t.includes('Rare'))
    )
  })

  it('많으면 잘라 그리되 몇 개가 더 있는지 말한다', async () => {
    // **조용히 자르지 않는다.** 안 보이는 값이 있다는 것을 모르면 사람은
    // "그 분류가 없다" 로 읽는다.
    const user = userEvent.setup()
    render(<OptionPicker label="Category" value="" options={many(200)} onChange={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /전체/ }))
    expect(await screen.findByText(/140개 더 있습니다/)).toBeInTheDocument()
  })

  it('없으면 없다고 말한다', async () => {
    const user = userEvent.setup()
    render(
      <OptionPicker
        label="Family"
        value=""
        options={[{ value: 'Metal', count: 1 }]}
        onChange={vi.fn()}
      />
    )
    await user.click(screen.getByRole('button', { name: /전체/ }))
    await user.type(await screen.findByPlaceholderText('Family 찾기'), 'zzz')
    expect(await screen.findByText(/맞는 Family 이\(가\) 없습니다/)).toBeInTheDocument()
  })

  it('고르면 알려 주고 닫는다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <OptionPicker
        label="Family"
        value=""
        options={[{ value: 'Polymer', count: 4 }]}
        onChange={onChange}
      />
    )
    await user.click(screen.getByRole('button', { name: /전체/ }))
    await user.click(await screen.findByText('Polymer'))
    expect(onChange).toHaveBeenCalledWith('Polymer')
  })
})
