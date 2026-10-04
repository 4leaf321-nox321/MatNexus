/**
 * 승인 대기 값 — 모아서 보이고, **자료 관리자는 그 자리에서 승인한다**(2026-10-04).
 *
 *   근거를 더 볼 자리로 링크한다    재료 값은 「물성」 탭, 시료 값(밀시트)은 「시료·시편」 탭
 *   승인 단추는 자료 관리자에게만   판정은 서버지만, 눌러 보고 403 을 알게 하지 않는다
 *   무엇을 승인하는지 다시 보인다    긴 목록에서 옆 줄을 눌러도 알 수 있게
 *   보던 값을 승인한다              줄의 지문을 함께 보낸다 — 그 사이 바뀌었으면 서버가 막는다
 *   방금 한 것은 되돌린다           목록에서 빠지므로 그 자리에서
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DeclaredReviewPage from '@/modules/materials/DeclaredReviewPage'

const declaredReview = vi.fn()
const approveDeclared = vi.fn()
const unapproveDeclared = vi.fn()
const approveSampleDeclared = vi.fn()
const unapproveSampleDeclared = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    declaredReview: (...args: unknown[]) => declaredReview(...args),
    approveDeclared: (...args: unknown[]) => approveDeclared(...args),
    unapproveDeclared: (...args: unknown[]) => unapproveDeclared(...args),
    approveSampleDeclared: (...args: unknown[]) => approveSampleDeclared(...args),
    unapproveSampleDeclared: (...args: unknown[]) => unapproveSampleDeclared(...args),
  },
}))

/** 지금 들어온 사람 — 시험마다 바꾼다. */
let me: Record<string, unknown> | null = null
vi.mock('@/shared/auth/AuthContext', () => ({
  useMaybeAuth: () => (me ? { user: me } : null),
  useAuth: () => ({ user: me }),
}))

const BASE = {
  source: 'literature',
  reference: 'ASM Handbook p.120',
  si_unit: 'Pa',
  point_count: 1,
  sample_id: null,
  sample_name: null,
  lot_no: null,
}

const ROWS = [
  {
    ...BASE,
    level: '재료',
    material_id: 'm1',
    material_name: 'SECC_-_1.0',
    item: '탄성계수',
    first_value_si: 2.0e11,
    quality_tier: 3,
    tier_if_approved: 2,
    digest: 'd1',
  },
  {
    ...BASE,
    level: '시료',
    material_id: 'm2',
    material_name: 'SPCC_-_1.2',
    sample_id: 's1',
    sample_name: 'SPCC_-_1.2_S01',
    lot_no: 'L-7',
    item: '인장강도',
    source: 'estimate',
    first_value_si: 4.2e8,
    point_count: 2,
    quality_tier: 4,
    tier_if_approved: 3,
    digest: 'd2',
  },
]

function show() {
  render(
    <MemoryRouter>
      <DeclaredReviewPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  me = null
  declaredReview.mockResolvedValue({ items: ROWS, total: 2, limit: 200, offset: 0 })
  approveDeclared.mockResolvedValue({})
  unapproveDeclared.mockResolvedValue({})
  approveSampleDeclared.mockResolvedValue({})
})

it('값을 화면 단위로 보이고, 근거를 더 볼 탭으로 링크한다', async () => {
  show()
  const material = await screen.findByRole('link', { name: 'SECC_-_1.0' })
  expect(material).toHaveAttribute('href', '/materials/m1?tab=properties')
  expect(screen.getByRole('link', { name: 'SPCC_-_1.2' })).toHaveAttribute(
    'href',
    '/materials/m2?tab=samples'
  )
  expect(screen.getByText('3 → 2')).toBeInTheDocument()
  expect(screen.getByText('4 → 3')).toBeInTheDocument()
  expect(screen.getByText('시료 · 로트 L-7')).toBeInTheDocument()
  expect(screen.getByText(/외 1점/)).toBeInTheDocument()
  // 첫 쪽만 읽고 끝내지 않는다 — 한 쪽 상한에서 자르면 나머지가 「없는」 것이 된다.
  expect(declaredReview).toHaveBeenCalledWith(200, 0)
})

it('자료 관리자가 아니면 승인 단추가 없다', async () => {
  me = { is_system_admin: false, is_data_manager: false }
  show()
  await screen.findByRole('link', { name: 'SECC_-_1.0' })
  expect(screen.queryByRole('button', { name: /승인/ })).not.toBeInTheDocument()
})

describe('자료 관리자는 그 자리에서 승인한다', () => {
  beforeEach(() => {
    me = { is_system_admin: false, is_data_manager: true }
  })

  it('무엇을 승인하는지 다시 보이고, 보던 값의 지문을 함께 보낸다', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'SECC_-_1.0 탄성계수 승인' }))
    const dialog = within(await screen.findByRole('dialog'))
    expect(dialog.getByText('ASM Handbook p.120')).toBeInTheDocument()
    expect(dialog.getByText('3 → 2')).toBeInTheDocument()
    // **삭제의 경고를 달지 않는다** — 승인은 되돌릴 수 있다.
    expect(dialog.getByText(/「되돌리기」 로 거둘 수 있습니다/)).toBeInTheDocument()
    expect(dialog.queryByText('되돌릴 수 없습니다.')).not.toBeInTheDocument()
    expect(approveDeclared).not.toHaveBeenCalled()

    await userEvent.type(dialog.getByLabelText('무엇을 확인했나'), '원문 대조')
    await userEvent.click(dialog.getByRole('button', { name: '승인' }))
    await waitFor(() =>
      expect(approveDeclared).toHaveBeenCalledWith('m1', '탄성계수', '원문 대조', 'd1')
    )
    // 목록을 다시 읽는다 — 승인한 줄은 빠진다.
    await waitFor(() => expect(declaredReview).toHaveBeenCalledTimes(2))
  })

  it('시료 값은 시료로 승인한다', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'SPCC_-_1.2 인장강도 승인' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '승인' }))
    await waitFor(() =>
      expect(approveSampleDeclared).toHaveBeenCalledWith('s1', '인장강도', undefined, 'd2')
    )
    expect(approveDeclared).not.toHaveBeenCalled()
  })

  it('방금 승인한 것은 그 자리에서 되돌린다', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'SECC_-_1.0 탄성계수 승인' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '승인' }))
    const done = within(await screen.findByLabelText('방금 승인한 값'))
    expect(done.getByText(/SECC_-_1.0 · 탄성계수/)).toBeInTheDocument()
    await userEvent.click(done.getByRole('button', { name: /되돌리기/ }))
    await waitFor(() => expect(unapproveDeclared).toHaveBeenCalledWith('m1', '탄성계수'))
    expect(await done.findByText(/승인을 거뒀습니다/)).toBeInTheDocument()
  })

  it('그 사이 값이 바뀌었으면 서버의 말을 창에 보이고 목록을 다시 읽는다', async () => {
    approveDeclared.mockRejectedValueOnce(new Error('값이 목록을 연 뒤에 바뀌었습니다'))
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'SECC_-_1.0 탄성계수 승인' }))
    const dialog = within(await screen.findByRole('dialog'))
    await userEvent.click(dialog.getByRole('button', { name: '승인' }))
    expect(await dialog.findByText(/목록을 연 뒤에 바뀌었습니다/)).toBeInTheDocument()
    await waitFor(() => expect(declaredReview).toHaveBeenCalledTimes(2))
  })
})
