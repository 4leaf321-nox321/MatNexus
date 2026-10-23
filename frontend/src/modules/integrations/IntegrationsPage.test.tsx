/**
 * 외부 연동 화면 — **토큰은 보내기만 하고, 빈 칸은 「그대로」 다**(2026-10-23).
 *
 *   토큰 칸은 늘 비어 있고 상태만 보인다      설정됨 · 풀지 못함 · 없음
 *   빈 칸으로 저장하면 token=null            주소만 고쳐도 토큰이 안 지워진다
 *   지우기는 따로 누른다                     clear_token
 *   연결 확인 결과가 한 줄로 선다             토큰 주인 · 물성 수
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import IntegrationsPage from '@/modules/integrations/IntegrationsPage'
import type { Integration } from '@/modules/integrations/api'

const list = vi.fn()
const save = vi.fn()
const check = vi.fn()

vi.mock('@/modules/integrations/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/integrations/api')>()),
  integrationsApi: {
    list: (...args: unknown[]) => list(...args),
    save: (...args: unknown[]) => save(...args),
    check: (...args: unknown[]) => check(...args),
  },
}))

const SET: Integration = {
  system: 'testscope',
  label: 'TestScope',
  base_url: 'http://testscope-host:8020/api',
  web_url: '',
  link_url: 'http://testscope-host:8020',
  has_token: true,
  token_readable: true,
  token_set_at: '2026-10-23T00:00:00Z',
  configured: true,
  checked_at: null,
  check_ok: null,
  check_message: null,
  updated_by: '관리자',
  updated_at: '2026-10-23T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  list.mockResolvedValue([SET])
  save.mockImplementation(async (_system: string, body: { base_url: string }) => ({
    ...SET,
    base_url: body.base_url,
  }))
})

describe('외부 연동', () => {
  it('토큰은 상태만 보이고, 빈 칸으로 저장하면 그대로 둔다', async () => {
    render(<IntegrationsPage />)
    const base = await screen.findByLabelText('API 주소')
    expect(base).toHaveValue('http://testscope-host:8020/api')
    expect(screen.getByLabelText('읽기 토큰')).toHaveValue('')
    expect(screen.getByText(/지금: 설정됨/)).toBeInTheDocument()

    fireEvent.change(base, { target: { value: 'http://testscope-new:8020' } })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(save).toHaveBeenCalledWith('testscope', {
      base_url: 'http://testscope-new:8020',
      web_url: '',
      token: null,
      clear_token: false,
    })
  })

  it('새 토큰은 보내고 칸을 비우며, 지우기는 따로 누른다', async () => {
    render(<IntegrationsPage />)
    const token = await screen.findByLabelText('읽기 토큰')
    fireEvent.change(token, { target: { value: ' tsp_new ' } })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(save.mock.calls[0][1]).toMatchObject({ token: 'tsp_new', clear_token: false })
    await waitFor(() => expect(screen.getByLabelText('읽기 토큰')).toHaveValue(''))

    fireEvent.click(screen.getByRole('button', { name: '토큰 지우기' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2))
    expect(save.mock.calls[1][1]).toMatchObject({ token: null, clear_token: true })
  })

  it('풀지 못하는 토큰은 다시 넣으라고 말하고, 연결 확인 결과가 선다', async () => {
    list.mockResolvedValue([{ ...SET, token_readable: false, configured: false }])
    check.mockResolvedValue({
      ok: true,
      message: '연결됨 — TestScope 사용자 「연동 계정」, 시험 항목이 이어진 물성 3개.',
      checked_at: '2026-10-23T01:00:00Z',
      who: '연동 계정',
      linked_properties: 3,
    })
    render(<IntegrationsPage />)
    expect(await screen.findByText(/풀지 못함 — 다시 넣으세요/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '연결 확인' }))
    expect(await screen.findByRole('status')).toHaveTextContent('연동 계정')
    expect(check).toHaveBeenCalledWith('testscope')
  })
})
