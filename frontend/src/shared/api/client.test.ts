/**
 * 오류 파서 — **여기서 오류가 나면 안 된다.**
 *
 * **실사용에서 걸렸다.** 삭제가 실패했는데 화면에 뜬 것은 원인이 아니라
 * `Cannot read properties of undefined (reading 'message')` 였다. 서버가 봉투가
 * 아닌 JSON(`{"detail": ...}`)을 냈고, 파서가 `body.error.message` 를 읽다가
 * 터진 것이다.
 *
 * 그러면 사람은 **요청이 왜 실패했는지가 아니라 프론트가 깨졌다고 읽는다.**
 * 오류를 알리는 길이 오류에 걸리면, 그 뒤로는 아무것도 설명되지 않는다.
 *
 * 서버 쪽도 함께 고쳤다(`app/shared/errors.py` 가 405 도 봉투에 담는다). 그래도
 * 여기를 막아 두는 이유: **파서는 서버가 무엇을 보내든 살아남아야 한다.** 프록시나
 * 게이트웨이가 끼면 우리 봉투가 아닌 것이 온다.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from '@/shared/api/client'

function answer(status: number, body: string, type = 'application/json') {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(body, { status, headers: { 'Content-Type': type } })
    )
  )
}

describe('오류 파서', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('봉투는 그대로 읽는다', async () => {
    answer(403, JSON.stringify({ error: { code: 'MNX-VOC-0003', message: '자기 것만' } }))
    const caught = await api.delete('/voc/1').catch((error: unknown) => error)
    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).code).toBe('MNX-VOC-0003')
    expect((caught as ApiError).message).toBe('자기 것만')
  })

  it('봉투가 아닌 JSON 에서도 터지지 않고, 서버가 한 말을 살린다', async () => {
    // Starlette 이 내는 모양. 전에는 이 줄에서 TypeError 가 났다.
    answer(405, JSON.stringify({ detail: 'Method Not Allowed' }))
    const caught = await api.delete('/voc/1').catch((error: unknown) => error)
    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).code).toBe('MNX-CLIENT-0001')
    // **버리지 않는다** — 이 말이 없으면 무엇이 잘못됐는지가 통째로 사라진다.
    expect((caught as ApiError).message).toContain('Method Not Allowed')
    expect((caught as ApiError).message).toContain('405')
  })

  it('JSON 이 아니어도 터지지 않는다', async () => {
    // 프록시가 끼면 HTML 오류 페이지가 온다.
    answer(502, '<html>Bad Gateway</html>', 'text/html')
    const caught = await api.get('/voc').catch((error: unknown) => error)
    expect((caught as ApiError).code).toBe('MNX-CLIENT-0001')
    expect((caught as ApiError).status).toBe(502)
  })

  it('반쯤 맞는 봉투도 봉투가 아니다', async () => {
    // `code` 만 있고 `message` 가 없으면 읽는 순간 `undefined` 가 화면에 뜬다.
    answer(400, JSON.stringify({ error: { code: 'MNX-X-0001' } }))
    const caught = await api.get('/voc').catch((error: unknown) => error)
    expect((caught as ApiError).code).toBe('MNX-CLIENT-0001')
  })

  it('204 는 본문을 읽지 않는다', async () => {
    // 삭제의 정상 응답이다. 여기서 JSON 을 파싱하려 들면 성공이 실패로 뒤집힌다.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(api.delete('/voc/1')).resolves.toBeUndefined()
  })
})
