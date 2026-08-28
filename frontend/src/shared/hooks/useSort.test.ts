/**
 * 정렬 기억 — **브라우저가 기억하되, 믿지는 않는다.**
 *
 * 무는 자리를 「기억한다」 보다 **「이상한 것이 적혀 있어도 화면이 산다」** 에
 * 둔다. 앞엣것은 안 되면 바로 보이지만, 뒤엣것은 **그 브라우저에서만** 목록이
 * 안 뜨고 사람은 자기 것만 고장 난 이유를 알 수 없다.
 */

import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSort } from '@/shared/hooks/useSort'

const ALLOWED = ['created_at', 'record_name', 'standard'] as const
const KEY = 'matnexus.sort.demo'

beforeEach(() => {
  window.localStorage.clear()
  vi.restoreAllMocks()
})

describe('누르는 규칙', () => {
  it('기본은 준 열의 내림차순', () => {
    const { result } = renderHook(() => useSort('created_at'))
    expect(result.current.sort).toEqual({ key: 'created_at', descending: true })
  })

  it('같은 열을 다시 누르면 뒤집는다', () => {
    const { result } = renderHook(() => useSort('created_at'))
    act(() => result.current.handle('created_at').onSort('created_at'))
    expect(result.current.sort.descending).toBe(false)
  })

  it('다른 열은 내림차순부터', () => {
    // 최근 것이 궁금한 열이 많다 — 오름차순부터면 거의 매번 두 번 눌러야 한다.
    const { result } = renderHook(() => useSort('created_at'))
    act(() => result.current.handle('created_at').onSort('created_at'))
    act(() => result.current.handle('record_name').onSort('record_name'))
    expect(result.current.sort).toEqual({ key: 'record_name', descending: true })
  })
})

describe('기억하기', () => {
  it('이름을 안 주면 안 적는다', () => {
    const { result } = renderHook(() => useSort('created_at'))
    act(() => result.current.handle('record_name').onSort('record_name'))
    expect(window.localStorage.length).toBe(0)
  })

  it('이름을 주면 적고 다시 읽는다', () => {
    const first = renderHook(() => useSort('created_at', { remember: 'demo' }))
    act(() => first.result.current.handle('record_name').onSort('record_name'))

    const second = renderHook(() => useSort('created_at', { remember: 'demo' }))
    expect(second.result.current.sort).toEqual({ key: 'record_name', descending: true })
  })

  it('표마다 따로 기억한다', () => {
    // 재료를 이름순으로 본다고 시편까지 그래야 할 이유가 없다.
    const one = renderHook(() => useSort('created_at', { remember: 'a' }))
    act(() => one.result.current.handle('record_name').onSort('record_name'))

    const two = renderHook(() => useSort('created_at', { remember: 'b' }))
    expect(two.result.current.sort.key).toBe('created_at')
  })
})

describe('적힌 것을 믿지 않는다', () => {
  it('지금 없는 열이면 버린다', () => {
    /**
     * **여기가 제일 위험한 자리다.** 표에서 열을 빼면 서버가 422 를 내고,
     * 그러면 그 브라우저에서만 목록이 영영 안 뜬다.
     */
    window.localStorage.setItem(KEY, JSON.stringify({ key: '없어진열', descending: true }))
    const { result } = renderHook(() =>
      useSort('created_at', { remember: 'demo', allowed: ALLOWED })
    )
    expect(result.current.sort.key).toBe('created_at')
  })

  it('모양이 깨졌으면 버린다', () => {
    window.localStorage.setItem(KEY, '{ 이건 JSON 이 아니다')
    const { result } = renderHook(() => useSort('created_at', { remember: 'demo' }))
    expect(result.current.sort.key).toBe('created_at')
  })

  it('타입이 다르면 버린다', () => {
    window.localStorage.setItem(KEY, JSON.stringify({ key: 3, descending: 'yes' }))
    const { result } = renderHook(() => useSort('created_at', { remember: 'demo' }))
    expect(result.current.sort.key).toBe('created_at')
  })

  it('저장소를 못 읽어도 화면은 산다', () => {
    // 개인 정보 보호 모드에서는 접근 자체가 던진다. **정렬 하나 때문에 화면이
    // 죽으면 안 된다.**
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('막힘')
    })
    const { result } = renderHook(() => useSort('created_at', { remember: 'demo' }))
    expect(result.current.sort.key).toBe('created_at')
  })

  it('저장소에 못 써도 이번 화면은 그대로 돈다', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('꽉 참')
    })
    const { result } = renderHook(() => useSort('created_at', { remember: 'demo' }))
    act(() => result.current.handle('record_name').onSort('record_name'))
    expect(result.current.sort.key).toBe('record_name')
  })
})
