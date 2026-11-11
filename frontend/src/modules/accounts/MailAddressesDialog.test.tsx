/**
 * 메일 주소 복사 — **HTTP(보안 컨텍스트 아님)에서도 누른 그 순간에 복사된다.**
 *
 * 클립보드를 흉내 내지 않고 진짜 `shared/lib/clipboard` 를 쓴다 — 운영 서버가 HTTP 라 되돌아 가는
 * 길(숨은 칸 + `execCommand('copy')`)이 실제로 그 글을, 대화상자 안에서 복사하는지가 이 시험의 전부다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Account } from '@/modules/accounts/api'
import { MailAddressesDialog } from '@/modules/accounts/MailAddressesDialog'
import { mailAddresses } from '@/modules/accounts/mailAddresses'

function account(over: Partial<Account>): Account {
  return {
    id: 'u1',
    email: 'hong@samsung.com',
    display_name: '홍길동',
    status: 'active',
    is_system_admin: false,
    is_data_manager: false,
    must_change_password: false,
    home_workspace_slug: null,
    requested_workspace_slug: null,
    memberships: [],
    created_at: '2026-09-01T00:00:00Z',
    decided_at: null,
    decision_note: null,
    deleted_at: null,
    ...over,
  }
}

const PICKED = [
  account({ id: 'a', email: 'hong@samsung.com', display_name: '홍길동' }),
  account({ id: 'b', email: 'kim@samsung.com', display_name: '김철수' }),
  account({ id: 'c', email: 'admin', display_name: '관리자' }),
]

describe('mailAddresses', () => {
  it('주소를 ; 로 잇고, 메일이 안 가는 계정은 까닭과 함께 뺀다', () => {
    const made = mailAddresses([
      ...PICKED,
      account({ id: 'd', email: 'HONG@samsung.com ', display_name: '같은 주소' }),
      account({
        id: 'e',
        email: 'park@samsung.com#deleted-20260918T030000Z',
        display_name: '박지운',
        deleted_at: '2026-09-18T03:00:00Z',
      }),
    ])
    expect(made.text).toBe('hong@samsung.com; kim@samsung.com')
    expect(made.skipped).toEqual([
      { name: '관리자', why: '메일 주소가 아닌 아이디(admin)' },
      { name: '박지운', why: '삭제된 계정' },
    ])
  })
})

describe('HTTP 에서 복사', () => {
  /** `execCommand('copy')` 가 불린 순간의 숨은 칸 — 무엇을, 어디서 복사했나. */
  let seen: { text: string; inDialog: boolean } | null = null

  beforeEach(() => {
    seen = null
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
  })

  afterEach(() => {
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
  })

  function stubCopy(result: boolean) {
    document.execCommand = vi.fn(() => {
      const box = document.querySelector('textarea[aria-hidden="true"]') as HTMLTextAreaElement
      seen = box ? { text: box.value, inDialog: Boolean(box.closest('[role="dialog"]')) } : null
      return result
    })
  }

  it('누르면 그 자리에서 주소 한 줄을 복사하고, 대화상자 안에서 복사한다', async () => {
    stubCopy(true)
    const user = userEvent.setup()
    render(<MailAddressesDialog accounts={PICKED} onClose={() => {}} />)
    const dialog = await screen.findByRole('dialog')
    const box = within(dialog).getByLabelText('메일 주소') as HTMLTextAreaElement
    expect(box.value).toBe('hong@samsung.com; kim@samsung.com')
    expect(within(dialog).getByRole('status')).toHaveTextContent('2명')
    expect(within(dialog).getByRole('status')).toHaveTextContent('관리자(메일 주소가 아닌 아이디(admin))')

    await user.click(within(dialog).getByRole('button', { name: '복사' }))
    await waitFor(() => expect(document.execCommand).toHaveBeenCalledWith('copy'))
    // 모달 밖(body)에 숨은 칸을 붙이면 Radix 가 가려 빈 것이 복사된다 — 안에서 복사해야 한다.
    expect(seen).toEqual({ text: 'hong@samsung.com; kim@samsung.com', inDialog: true })
    expect(await within(dialog).findByRole('button', { name: '복사했습니다' })).toBeInTheDocument()
  })

  it('브라우저가 막으면 직접 복사하는 길을 말한다', async () => {
    stubCopy(false)
    const user = userEvent.setup()
    render(<MailAddressesDialog accounts={PICKED} onClose={() => {}} />)
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: '복사' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Ctrl+C')
  })
})
