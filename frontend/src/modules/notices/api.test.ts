/**
 * 읽음을 적는 함수가 **직접 알린다**(`NOTICES_READ`) — 사이드바의 수가 그것을 듣고 곧바로
 * 다시 센다. 읽음을 적는 자리가 여럿이라(상세 · 로그인 팝업 · 「모두 읽음」) 화면마다 알리게
 * 두면 한 곳은 빠진다.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { NOTICES_READ, noticesApi } from '@/modules/notices/api'

const post = vi.fn()

vi.mock('@/shared/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/api/client')>()
  return {
    ...actual,
    api: { ...actual.api, post: (...args: unknown[]) => post(...args) },
  }
})

describe('읽음 신호', () => {
  const heard = vi.fn()

  afterEach(() => {
    window.removeEventListener(NOTICES_READ, heard)
  })

  it('한 건을 읽으면 알린다', async () => {
    window.addEventListener(NOTICES_READ, heard)
    post.mockResolvedValue(undefined)
    await noticesApi.read('n1')
    expect(post).toHaveBeenCalledWith('/notices/n1/read')
    expect(heard).toHaveBeenCalledTimes(1)
  })

  it('모두 읽음도 알리고, 서버의 답을 그대로 돌려준다', async () => {
    window.addEventListener(NOTICES_READ, heard)
    post.mockResolvedValue({ unread: 0 })
    await expect(noticesApi.readAll()).resolves.toEqual({ unread: 0 })
    expect(heard).toHaveBeenCalledTimes(1)
  })

  it('실패하면 알리지 않는다 — 안 읽은 채인데 수만 다시 세게 하지 않는다', async () => {
    window.addEventListener(NOTICES_READ, heard)
    post.mockRejectedValue(new Error('끊김'))
    await expect(noticesApi.read('n1')).rejects.toThrow('끊김')
    expect(heard).not.toHaveBeenCalled()
  })
})
