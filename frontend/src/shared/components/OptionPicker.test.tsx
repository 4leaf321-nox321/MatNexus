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

  describe('서버 검색 모드', () => {
    it('타이핑이 멎으면 서버에 묻고, 서버가 준 것을 그대로 보여 준다', async () => {
      const user = userEvent.setup()
      // **서버가 별칭으로 찾아 준 것을 브라우저가 또 거르면 안 된다.**
      // '포스코주' 로 쳤는데 서버가 '포스코' 를 돌려주면 그걸 보여야 한다.
      const search = vi.fn().mockResolvedValue([{ value: '포스코', count: 12 }])
      render(
        <OptionPicker
          label="제조사"
          value=""
          options={[]}
          search={search}
          onChange={vi.fn()}
        />
      )
      await user.click(screen.getByRole('button', { name: /전체/ }))
      await user.type(screen.getByPlaceholderText('제조사 찾기'), '포스코주')

      await waitFor(() => expect(screen.getByText('포스코')).toBeInTheDocument())
      expect(search).toHaveBeenCalledWith('포스코주')
    })

    it('늦게 온 응답이 최신 결과를 덮지 않는다', async () => {
      const user = userEvent.setup()
      // 'S' 의 응답이 'SECC' 보다 늦게 오는 상황. 실제로 생긴다 — 짧은 검색어가
      // 더 많은 행을 훑어서 오히려 느릴 수 있다.
      // 담아 두는 그릇을 쓴다 — `let x = null` 은 콜백 안의 대입을 타입 검사가
      // 못 보고 계속 null 로 좁힌다.
      const slow: { resolve?: (value: { value: string }[]) => void } = {}
      const search = vi
        .fn()
        .mockImplementationOnce(
          () => new Promise<{ value: string }[]>((r) => (slow.resolve = r))
        )
        .mockResolvedValue([{ value: 'SECC180' }])

      render(
        <OptionPicker label="강종" value="" options={[]} search={search} onChange={vi.fn()} />
      )
      await user.click(screen.getByRole('button', { name: /전체/ }))
      const box = screen.getByPlaceholderText('강종 찾기')
      await user.type(box, 'S')
      await waitFor(() => expect(search).toHaveBeenCalledTimes(1))
      await user.type(box, 'ECC')
      await waitFor(() => expect(screen.getByText('SECC180')).toBeInTheDocument())

      // 이제 뒤늦게 'S' 의 응답이 온다.
      slow.resolve?.([{ value: '늦게 온 것' }])
      await waitFor(() => expect(screen.getByText('SECC180')).toBeInTheDocument())
      expect(screen.queryByText('늦게 온 것')).not.toBeInTheDocument()
    })

    it('만들기가 꺼져 있으면 새로 추가를 안 보여 준다', async () => {
      const user = userEvent.setup()
      // 기준정보 관리에서 상위 분류를 고를 때 쓴다 — 부모는 이미 있는 값이어야 하고,
      // 강종의 부모를 손보다가 Family 를 새로 만드는 것은 아무도 의도하지 않는다.
      const search = vi.fn().mockResolvedValue([])
      render(
        <OptionPicker
          label="상위 분류"
          value=""
          options={[]}
          search={search}
          onChange={vi.fn()}
        />
      )
      await user.click(screen.getByRole('button', { name: /전체/ }))
      await user.type(screen.getByPlaceholderText('상위 분류 찾기'), '없는값')
      await waitFor(() => expect(search).toHaveBeenCalled())
      expect(screen.queryByText(/새로 추가/)).not.toBeInTheDocument()
    })

    it('만들기가 켜져 있으면 새로 추가가 뜬다', async () => {
      const user = userEvent.setup()
      const search = vi.fn().mockResolvedValue([])
      const onCreate = vi.fn().mockResolvedValue({ value: '만든값' })
      render(
        <OptionPicker
          label="강종"
          value=""
          options={[]}
          search={search}
          onCreate={onCreate}
          onChange={vi.fn()}
        />
      )
      await user.click(screen.getByRole('button', { name: /전체/ }))
      await user.type(screen.getByPlaceholderText('강종 찾기'), '새강종')
      await waitFor(() => expect(search).toHaveBeenCalled())
      await user.click(await screen.findByText(/새로 추가/))
      expect(onCreate).toHaveBeenCalledWith('새강종')
    })

    it('열기 전에는 서버를 안 부른다', () => {
      const search = vi.fn().mockResolvedValue([])
      render(
        <OptionPicker label="강종" value="" options={[]} search={search} onChange={vi.fn()} />
      )
      expect(search).not.toHaveBeenCalled()
    })
  })
})
