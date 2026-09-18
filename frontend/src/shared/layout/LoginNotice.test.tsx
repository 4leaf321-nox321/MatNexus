import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { LOGIN_NOTICE_KEY } from '@/shared/auth/AuthContext'
import { LoginNotice } from '@/shared/layout/LoginNotice'

describe('로그인 안내', () => {
  beforeEach(() => sessionStorage.clear())

  it('놓인 안내를 한 번 보이고 지운다', async () => {
    // 로그인 화면은 성공하면 바로 떠난다 — 껍데기가 대신 보여 준다.
    sessionStorage.setItem(LOGIN_NOTICE_KEY, "아이디에 @samsung.com 이 붙어 지금은 'hong@samsung.com' 입니다.")
    render(<LoginNotice />)
    expect(screen.getByRole('status')).toHaveTextContent('@samsung.com 이 붙어')
    expect(sessionStorage.getItem(LOGIN_NOTICE_KEY)).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '안내 닫기' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('안내가 없으면 아무것도 안 그린다', () => {
    render(<LoginNotice />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
