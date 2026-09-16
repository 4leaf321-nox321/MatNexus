/**
 * 가입 신청 — **회사 메일로만.** 규칙은 서버가 정하고(`/accounts/signup-policy`) 화면은
 * 치기 전에 보여 주고, 보내기 전에 한 번 더 본다. 서버도 같은 규칙으로 막는다(422).
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SignupPage from '@/modules/auth/SignupPage'

const signup = vi.fn()
const signupPolicy = vi.fn()

vi.mock('@/modules/accounts/api', () => ({
  accountsApi: {
    signup: (...args: unknown[]) => signup(...args),
    signupPolicy: (...args: unknown[]) => signupPolicy(...args),
  },
}))

vi.mock('@/modules/workspaces/api', () => ({
  workspacesApi: { options: () => Promise.resolve([]) },
}))

function show() {
  render(
    <MemoryRouter>
      <SignupPage />
    </MemoryRouter>,
  )
}

async function fill(email: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('아이디'), email)
  await user.type(screen.getByLabelText('이름'), '홍길동')
  // required 칸을 다 채워야 폼이 submit 된다 — 검사 순서는 그 다음 이야기다.
  await user.type(screen.getByLabelText('비밀번호'), 'applicant-password-1')
  await user.type(screen.getByLabelText('비밀번호 확인'), 'applicant-password-1')
  await user.click(screen.getByRole('button', { name: '신청하기' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  signupPolicy.mockResolvedValue({ email_domains: ['samsung.com'] })
})

describe('회사 메일로만', () => {
  it('치기 전에 규칙이 보인다', async () => {
    show()
    expect(await screen.findByText(/@samsung\.com.*로만 신청/)).toBeInTheDocument()
    expect(screen.getByLabelText('아이디')).toHaveAttribute('placeholder', '이름@samsung.com')
  })

  it('다른 도메인은 보내기 전에 막는다', async () => {
    show()
    await screen.findByText(/@samsung\.com.*로만 신청/)
    await fill('hong@gmail.com')
    // 안내문과 오류가 같은 문장 — 둘 다 보인다.
    await waitFor(() => expect(screen.getAllByText(/@samsung\.com.*로만 신청/)).toHaveLength(2))
    expect(signup).not.toHaveBeenCalled()
  })

  it('회사 메일은 통과한다 — 다음 검사(비밀번호·부서)로 간다', async () => {
    show()
    await screen.findByText(/@samsung\.com.*로만 신청/)
    await fill('Hong.GD@Samsung.com')
    expect(await screen.findByText('소속 부서를 선택하세요.')).toBeInTheDocument()
    expect(screen.getAllByText(/@samsung\.com.*로만 신청/)).toHaveLength(1)
  })

  it('규칙이 비어 있으면 제한하지 않는다', async () => {
    signupPolicy.mockResolvedValue({ email_domains: [] })
    show()
    await waitFor(() => expect(signupPolicy).toHaveBeenCalled())
    expect(screen.queryByText(/로만 신청/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('아이디')).toHaveAttribute('placeholder', '이메일 또는 아이디')
  })
})
