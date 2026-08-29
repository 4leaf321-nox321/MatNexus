/**
 * 핸드북 편집기의 그림 — **본문의 주소를 그대로 `<img>` 에 넣으면 안 된다.**
 *
 * 이 시험이 없어서 그림 75개가 전부 401 인 채로 배포됐다. 백엔드 시험은 있었지만
 * `headers=admin_headers` 로 받고 있었다 — **브라우저는 그 헤더를 안 보낸다.**
 * 시험이 브라우저가 아닌 것을 흉내내면 초록인 채로 고장 난다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuideEditor } from '@/modules/guide/GuideEditor'
import { clearAssetCache } from '@/modules/guide/assets'

const fetchWithAuth = vi.fn()
const revoked = vi.fn()
vi.mock('@/shared/api/client', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args),
  api: { get: vi.fn(), post: vi.fn() },
}))

const RAW = '/api/guide/assets/2f0a1b3c-0000-4000-8000-000000000001'
const DOC = {
  type: 'doc',
  content: [{ type: 'image', attrs: { src: RAW, alt: '겹치기 이음의 전단응력 분포' } }],
}

beforeEach(() => {
  clearAssetCache()
  fetchWithAuth.mockReset()
  // **되돌리지 않는다.** jsdom 에 아예 없는 함수라 `stubGlobal` 로 넣었다 빼면
  // 화면을 치우는 정리(노드뷰의 `destroy`)가 그 뒤에 돌면서 터진다.
  URL.createObjectURL = () => 'blob:fake/1'
  URL.revokeObjectURL = revoked
  revoked.mockReset()
})

describe('그림', () => {
  it('본문의 주소를 그대로 쓰지 않는다 — 그러면 토큰이 안 실려 401 이다', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'image/svg+xml' },
      text: () => Promise.resolve('<svg viewBox="0 0 4 4"><path/></svg>'),
    })
    render(<GuideEditor content={DOC} />)

    const image = await screen.findByAltText(/겹치기 이음/)
    await waitFor(() => expect(image).toHaveAttribute('src', 'blob:fake/1'))
    expect(image.getAttribute('src')).not.toBe(RAW)
    expect(fetchWithAuth).toHaveBeenCalledWith(RAW)
  })

  it('화면을 떠나도 blob 주소를 놓지 않는다 — 캐시가 그것을 들고 있다', async () => {
    // **실측(2026-08-29):** 그 자리에서 새로고침하면 보이는데 다른 데 갔다 오면
    // 안 보였다. 떠날 때 해제했는데 캐시는 그 문자열을 그대로 갖고 있어서, 돌아
    // 왔을 때 **이미 죽은 주소**를 돌려줬다. 새로고침은 모듈 캐시까지 비우니
    // 다시 받았고 — 그래서 「가끔 된다」 로 보였다.
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'image/svg+xml' },
      text: () => Promise.resolve('<svg viewBox="0 0 4 4"><path/></svg>'),
    })
    const view = render(<GuideEditor content={DOC} />)
    await screen.findByAltText(/겹치기 이음/)

    view.unmount() // 다른 화면으로 간다
    expect(revoked).not.toHaveBeenCalled()
  })

  it('돌아오면 다시 안 받는다 — 같은 주소를 그대로 쓴다', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      headers: { get: () => 'image/svg+xml' },
      text: () => Promise.resolve('<svg viewBox="0 0 4 4"><path/></svg>'),
    })
    const first = render(<GuideEditor content={DOC} />)
    await screen.findByAltText(/겹치기 이음/)
    first.unmount()

    render(<GuideEditor content={DOC} />)
    const again = await screen.findByAltText(/겹치기 이음/)
    await waitFor(() => expect(again).toHaveAttribute('src', 'blob:fake/1'))
    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
  })

  it('못 불러오면 그렇게 말한다 — 빈자리는 그림이 없는 것과 구별이 안 된다', async () => {
    fetchWithAuth.mockResolvedValue({ ok: false, status: 401, headers: { get: () => '' } })
    render(<GuideEditor content={DOC} />)

    const failed = await screen.findByAltText(/겹치기 이음.*401/)
    expect(failed).not.toHaveAttribute('src')
  })
})
