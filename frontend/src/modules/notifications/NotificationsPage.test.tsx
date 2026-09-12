/**
 * 알림함 — **끄고 켜는 자리가 있고, 끄면 서버로 나간다.**
 *
 * VOC 알림이 붙으면서 모든 계정이 알림을 받는다. 끌 길이 없으면 소음이 되고,
 * 소음이 되면 진짜 알림도 안 읽는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NotificationsPage from '@/modules/notifications/NotificationsPage'

const list = vi.fn()
const rules = vi.fn()
const setRule = vi.fn()

vi.mock('@/modules/notifications/api', () => ({
  notificationsApi: {
    list: (...args: unknown[]) => list(...args),
    rules: (...args: unknown[]) => rules(...args),
    setRule: (...args: unknown[]) => setRule(...args),
    read: vi.fn(),
    readAll: vi.fn(),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  list.mockResolvedValue([])
  rules.mockResolvedValue([
    {
      event_kind: 'voc.changed',
      label: '내 VOC 가 움직임',
      description: '내가 낸 VOC 를 남이 옮기거나 말을 보탰을 때',
      enabled: true,
    },
    {
      event_kind: 'account.decided',
      label: '가입 결정',
      description: '내 가입 신청이 승인·거절됐을 때',
      enabled: false,
    },
  ])
  setRule.mockResolvedValue({})
})

describe('알림 설정', () => {
  it('받을 수 있는 알림이 켜짐 여부와 함께 서고, 끄면 서버로 나간다', async () => {
    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    )
    const voc = await screen.findByRole('checkbox', { name: '내 VOC 가 움직임' })
    expect(voc).toBeChecked()
    expect(screen.getByRole('checkbox', { name: '가입 결정' })).not.toBeChecked()

    await userEvent.click(voc)
    await waitFor(() => expect(setRule).toHaveBeenCalledWith('voc.changed', false))
  })
})
