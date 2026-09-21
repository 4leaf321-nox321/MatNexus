/**
 * 「새로 추가」 를 **누구에게 보여 주나** (ADR 0032).
 *
 * `managed` 축은 이미 있는 값이면 누구나 고르지만 새 값은 부서 관리자만 세운다.
 * 서버가 403 으로 막으므로 여기서 지키는 것은 권한이 아니라 **눌러 보고 알게
 * 하지 않는 것**이다 — 그리고 안 보여 줄 때는 **왜인지 말하는 것**. 빈자리로
 * 두면 사람은 화면이 고장 났는지 원래 못 하는 일인지 구별하지 못한다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { forgetAxisPolicies, mayCoin } from '@/modules/vocabulary/entryPolicy'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'

const list = vi.fn()
const search = vi.fn()
const create = vi.fn()

vi.mock('@/modules/vocabulary/api', () => ({
  vocabularyApi: {
    list: () => list(),
    search: (...args: unknown[]) => search(...args),
    create: (...args: unknown[]) => create(...args),
  },
}))

let manager = false

vi.mock('@/shared/auth/AuthContext', () => ({
  useMaybeAuth: () => ({
    user: { is_system_admin: false, memberships: [{ role: manager ? 'manager' : 'member' }] },
  }),
}))

const AXES = [
  { slug: 'grade', label: 'Grade', entry_policy: 'managed', parent_slug: 'category' },
  { slug: 'lot_note', label: '메모', entry_policy: 'open', parent_slug: null },
]

beforeEach(() => {
  forgetAxisPolicies()
  manager = false
  list.mockReset()
  list.mockResolvedValue(AXES)
  search.mockReset()
  search.mockResolvedValue({ items: [], total: 0 })
  create.mockReset()
  create.mockResolvedValue({ value: '새등급', usage_count: 0 })
})

/** 피커를 열고 목록에 없는 값을 친다 — 「새로 추가」 가 뜨는 조건이다. */
async function typeNew(slug: string, label: string, text: string) {
  const user = userEvent.setup()
  render(<VocabularyField slug={slug} label={label} value="" onChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: /고르지 않음/ }))
  await user.type(screen.getByPlaceholderText(`${label} 찾기`), text)
  await waitFor(() => expect(search).toHaveBeenCalled())
  return user
}

describe('관리되는 축의 「새로 추가」', () => {
  it('일반 사용자에게는 안 보이고, 대신 누구에게 부탁할지가 보인다', async () => {
    await typeNew('grade', 'Grade', '새등급')

    expect(await screen.findByText(/부서 관리자만/)).toBeInTheDocument()
    expect(screen.queryByText(/새로 추가/)).not.toBeInTheDocument()
  })

  it('부서 관리자에게는 보인다', async () => {
    manager = true
    const user = await typeNew('grade', 'Grade', '새등급')

    await user.click(await screen.findByText(/새로 추가/))
    expect(create).toHaveBeenCalledWith('grade', '새등급', undefined)
  })

  it('open 축은 누구나 그대로 만든다 — 로트·메모까지 막으면 아무 일도 못 한다', async () => {
    const user = await typeNew('lot_note', '메모', '깨짐 있음')

    await user.click(await screen.findByText(/새로 추가/))
    expect(create).toHaveBeenCalled()
  })

  it('서버가 그래도 막으면 서버의 말을 보여 준다', async () => {
    // 화면의 판정이 서버와 어긋날 수 있다 — 권한이 방금 바뀌었거나, 축 목록을
    // 못 받아 왔거나. 조용히 아무 일도 안 일어나면 단추가 고장 난 것처럼 보인다.
    manager = true
    create.mockRejectedValue(new Error("'Grade' 에 새 값을 세우는 것은 부서 관리자만"))
    const user = await typeNew('grade', 'Grade', '새등급')

    await user.click(await screen.findByText(/새로 추가/))
    expect(await screen.findByText(/부서 관리자만/)).toBeInTheDocument()
  })

  it('축 목록은 피커가 몇이든 한 번만 받는다', async () => {
    render(
      <>
        <VocabularyField slug="grade" label="Grade" value="" onChange={vi.fn()} />
        <VocabularyField slug="lot_note" label="메모" value="" onChange={vi.fn()} />
      </>
    )
    await waitFor(() => expect(list).toHaveBeenCalled())
    expect(list).toHaveBeenCalledTimes(1)
  })
})

describe('mayCoin', () => {
  it('managed 는 관리자만, open·closed 는 정책이 정한다', () => {
    expect(mayCoin('managed', false)).toBe(false)
    expect(mayCoin('managed', true)).toBe(true)
    expect(mayCoin('open', false)).toBe(true)
    expect(mayCoin('closed', true)).toBe(false)
  })

  it('모를 때는 감추지 않는다 — 판정은 서버가 한다', () => {
    // 로그인 정보가 없는 자리에 얹힌 피커(`useMaybeAuth` 가 null), 또는 축
    // 목록을 아직 못 받은 동안. 여기서 감추면 **관리자도 단추를 못 보고**
    // 그 원인은 화면 어디에도 안 적힌다.
    expect(mayCoin('managed', null)).toBe(true)
    expect(mayCoin(null, false)).toBe(true)
  })
})
