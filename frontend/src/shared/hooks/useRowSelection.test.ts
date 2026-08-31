/**
 * 줄 고르기 — **고른 것과 손대는 것이 어긋나지 않는다.**
 *
 * 이 훅이 내는 수를 화면이 「3건에 적용」 으로 보이고, 그 목록이 그대로 지우기·
 * 일괄 수정으로 간다. 무는 자리를 고를 때 「Shift 가 된다」 보다 **「안 보이는
 * 줄이 딸려 가지 않는다」** 를 우선한다 — 앞엣것은 안 되면 바로 보이지만,
 * 뒤엣것은 사람이 못 본 줄이 지워진다.
 */

import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useRowSelection } from '@/shared/hooks/useRowSelection'

const ROWS = ['a', 'b', 'c', 'd', 'e']

describe('한 줄씩', () => {
  it('누르면 켜지고 다시 누르면 꺼진다', () => {
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('b'))
    expect(result.current.chosen).toEqual(['b'])

    act(() => result.current.toggle('b'))
    expect(result.current.chosen).toEqual([])
  })

  it('여러 줄을 하나씩 켠다 — Ctrl 을 눌러도 같다', () => {
    // 체크박스는 원래 하나씩 토글한다. Ctrl 을 위한 규칙을 따로 만들지 않는다.
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('a'))
    act(() => result.current.toggle('d', { shiftKey: false }))

    expect(result.current.chosen).toEqual(['a', 'd'])
  })
})

describe('Shift 범위', () => {
  it('닻부터 지금까지를 켠다', () => {
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('b'))
    act(() => result.current.toggle('d', { shiftKey: true }))

    expect(result.current.chosen).toEqual(['b', 'c', 'd'])
  })

  it('거꾸로 눌러도 같다', () => {
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('d'))
    act(() => result.current.toggle('b', { shiftKey: true }))

    expect(result.current.chosen).toEqual(['b', 'c', 'd'])
  })

  it('범위는 켜기만 한다 — 끄지 않는다', () => {
    /** 파일 탐색기·메일함이 그렇고, 사람이 그것을 기대한다. */
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('a'))
    act(() => result.current.toggle('c'))
    // c 가 닻이다. c~e 를 Shift 로 켠다 — a 는 그대로 남는다.
    act(() => result.current.toggle('e', { shiftKey: true }))

    expect(result.current.chosen).toEqual(['a', 'c', 'd', 'e'])
  })

  it('껐던 줄에서도 이어진다', () => {
    // 닻은 「마지막으로 누른 줄」 이지 「마지막으로 켠 줄」 이 아니다.
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('b'))
    act(() => result.current.toggle('b')) // 껐다 — 그래도 닻이다
    act(() => result.current.toggle('d', { shiftKey: true }))

    expect(result.current.chosen).toEqual(['b', 'c', 'd'])
  })

  it('닻이 없으면 그냥 한 줄이다', () => {
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('c', { shiftKey: true }))

    expect(result.current.chosen).toEqual(['c'])
  })
})

describe('전부 고르기', () => {
  it('켜고 끈다', () => {
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.setAll(true))
    expect(result.current.allOn).toBe(true)
    expect(result.current.chosen).toEqual(ROWS)

    act(() => result.current.setAll(false))
    expect(result.current.chosen).toEqual([])
  })

  it('일부만 켜졌으면 someOn 이다', () => {
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('a'))

    expect(result.current.someOn).toBe(true)
    expect(result.current.allOn).toBe(false)
  })

  it('빈 목록은 allOn 이 아니다', () => {
    // 아무것도 없는데 머리 칸이 켜져 보이면 사람은 무언가 골랐다고 읽는다.
    const { result } = renderHook(() => useRowSelection([]))

    expect(result.current.allOn).toBe(false)
    expect(result.current.someOn).toBe(false)
  })
})

describe('목록이 바뀔 때', () => {
  it('안 보이는 줄은 안 딸려 간다', () => {
    /**
     * **여기가 제일 위험한 자리다.** 거르기를 바꿔 사라진 줄이 선택에 남아 있으면
     * 사람이 본 수와 실제로 지워지는 수가 어긋난다.
     */
    const { result, rerender } = renderHook(({ ids }) => useRowSelection(ids), {
      initialProps: { ids: ROWS },
    })

    act(() => result.current.setAll(true))
    expect(result.current.chosen).toHaveLength(5)

    rerender({ ids: ['a', 'c'] })

    expect(result.current.chosen).toEqual(['a', 'c'])
    expect(result.current.allOn).toBe(true)
  })

  it('돌아오면 다시 보인다', () => {
    // 잠깐 걸러 낸 것을 잊어버리면, 거르기를 되돌린 사람이 선택을 다시 해야 한다.
    const { result, rerender } = renderHook(({ ids }) => useRowSelection(ids), {
      initialProps: { ids: ROWS },
    })

    act(() => result.current.toggle('e'))
    rerender({ ids: ['a', 'b'] })
    expect(result.current.chosen).toEqual([])

    rerender({ ids: ROWS })
    expect(result.current.chosen).toEqual(['e'])
  })

  it('차례는 목록을 따른다', () => {
    // API 에 넘기는 순서가 화면과 다르면, 돌려받은 결과를 줄과 맞출 수 없다.
    const { result } = renderHook(() => useRowSelection(ROWS))

    act(() => result.current.toggle('d'))
    act(() => result.current.toggle('a'))

    expect(result.current.chosen).toEqual(['a', 'd'])
  })
})
