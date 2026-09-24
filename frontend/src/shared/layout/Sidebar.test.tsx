/**
 * 사이드바 머리글의 버전.
 *
 * **서버가 정본이다.** 번들에 박으면 그것은 *빌드된* 버전이지 *지금 도는* 서버가
 * 아니다 — 배포가 반쯤 끝났거나 서비스가 안 내려갔다 올라온 상태에서 둘이 갈리고,
 * 그때 화면이 거짓말을 한다. 답이 틀린 것은 못 답하는 것보다 나쁘다.
 */

import { act, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NOTICES_READ } from '@/modules/notices/api'
import { Sidebar } from '@/shared/layout/Sidebar'

const health = vi.fn()
const unreadCount = vi.fn()

vi.mock('@/shared/api/system', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/system')>()),
  systemApi: { health: () => health() },
}))

vi.mock('@/modules/notices/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/notices/api')>()),
  noticesApi: { unreadCount: () => unreadCount() },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: false, memberships: [] } }),
}))

function sidebar() {
  render(
    <MemoryRouter>
      <Sidebar collapsed={false} />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  health.mockResolvedValue({ status: 'ok', version: 'v1.73.0' })
  unreadCount.mockResolvedValue({ unread: 0 })
})

describe('사이드바 머리글', () => {
  it('서버가 준 버전을 보인다', async () => {
    sidebar()
    expect(await screen.findByText('v1.73.0')).toBeInTheDocument()
    expect(screen.getByText('MatNexus')).toBeInTheDocument()
  })

  it('못 찾았으면 안 적는다', async () => {
    // **`unknown` 을 그대로 띄우면 버전 자리가 고장난 것처럼 보인다.** 실제로는
    // 개발 경로에서 돈다는 뜻이다.
    health.mockResolvedValue({ status: 'ok', version: 'unknown' })
    sidebar()
    await waitFor(() => expect(health).toHaveBeenCalled())
    expect(screen.queryByText('unknown')).not.toBeInTheDocument()
  })

  it('서버가 이 빌드와 다른 버전이면 그 사실을 말한다', async () => {
    /**
     * **이게 없어서 하루를 날렸다**(2026-08-28). 개발과 운영이 같은 포트를 써서
     * 프론트가 옛 서버(v1.115.0)에 붙어 있었는데, 화면은 「존재하지 않는
     * 엔드포인트」 만 말했다. 버전은 이미 여기 떠 있었지만 **같은지 다른지를
     * 안 말해서** 아무도 못 봤다.
     */
    health.mockResolvedValue({ status: 'ok', version: 'v1.115.0' })
    sidebar()
    expect(await screen.findByText('v1.115.0')).toBeInTheDocument()
    expect(screen.getByText(`≠ ${__APP_VERSION__}`)).toBeInTheDocument()
  })

  it('같은 버전이면 조용하다', async () => {
    // **늘 경고하면 아무도 안 본다.** 맞을 때는 아무 말도 안 해야 다를 때가
    // 눈에 들어온다.
    health.mockResolvedValue({ status: 'ok', version: __APP_VERSION__ })
    sidebar()
    expect(await screen.findByText(__APP_VERSION__)).toBeInTheDocument()
    expect(screen.queryByText(/≠/)).not.toBeInTheDocument()
  })

  it('서버가 안 답해도 머리글은 뜬다', async () => {
    // 버전 하나 때문에 사이드바가 통째로 비면 안 된다.
    health.mockRejectedValue(new Error('끊김'))
    sidebar()
    expect(await screen.findByText('MatNexus')).toBeInTheDocument()
  })
})

/**
 * 안 읽은 공지 수 — 「공지 · VOC」 옆에 선다(2026-09-24).
 *
 * 팝업은 중요한 공지에만 켜므로, 나머지는 이 수가 아니면 게시판에 들어가 봐야 안다.
 */
describe('안 읽은 공지 수', () => {
  function noticeLink() {
    return screen.getByText('공지 · VOC').closest('a') as HTMLElement
  }

  it('안 읽은 공지가 있으면 그 수를 메뉴 옆에 단다', async () => {
    unreadCount.mockResolvedValue({ unread: 3 })
    sidebar()
    expect(await within(noticeLink()).findByText('3')).toBeInTheDocument()
    expect(within(noticeLink()).getByTitle('안 읽은 공지 3건')).toBeInTheDocument()
  })

  it('없으면 아무것도 안 단다', async () => {
    sidebar()
    await waitFor(() => expect(unreadCount).toHaveBeenCalled())
    expect(within(noticeLink()).queryByTitle(/안 읽은 공지/)).toBeNull()
  })

  it('많으면 99+ 로 줄인다', async () => {
    unreadCount.mockResolvedValue({ unread: 140 })
    sidebar()
    expect(await within(noticeLink()).findByText('99+')).toBeInTheDocument()
  })

  it('읽었다는 신호를 받으면 곧바로 다시 센다 — 1분을 기다리지 않는다', async () => {
    unreadCount.mockResolvedValue({ unread: 2 })
    sidebar()
    expect(await within(noticeLink()).findByText('2')).toBeInTheDocument()

    unreadCount.mockResolvedValue({ unread: 1 })
    act(() => {
      window.dispatchEvent(new Event(NOTICES_READ))
    })
    expect(await within(noticeLink()).findByText('1')).toBeInTheDocument()
  })
})
