/**
 * 기준정보 보기 — **누가 무엇까지 보는가.**
 *
 * 이 화면의 요점은 「목록이 뜬다」 가 아니라 **고치는 길이 안 열리는 것**이다.
 * 멤버에게 편집 단추가 보이면 눌러서 403 을 보고, 그러면 화면을 연 뜻이 없다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import VocabularyPage from '@/modules/vocabulary/VocabularyPage'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const list = vi.fn()
const search = vi.fn()
const units = vi.fn()
let isAdmin = false

vi.mock('@/modules/vocabulary/api', () => ({
  vocabularyApi: {
    list: () => list(),
    search: (...args: unknown[]) => search(...args),
  },
}))

vi.mock('@/modules/units/api', () => ({ unitsApi: { list: () => units() } }))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: isAdmin } }),
}))

const AXIS = {
  slug: 'manufacturer',
  label: '제조사',
  entry_policy: 'open',
  parent_slug: null,
  term_count: 2,
}

const term = (over: Record<string, unknown> = {}) => ({
  id: crypto.randomUUID(),
  value: '포스코',
  parent_value: null,
  status: 'active',
  usage_count: 12,
  attributes: {},
  extra_fields: [],
  field_count: 0,
  field_symbols: {},
  ratio_checks: [],
  ...over,
})

async function show(rows: unknown[], total = rows.length) {
  list.mockResolvedValue([AXIS])
  search.mockResolvedValue({ items: rows, total, limit: 100, offset: 0 })
  render(
    <MemoryRouter>
      <LeftPanelProvider>
        <LeftPanelHost />
        <VocabularyPage />
      </LeftPanelProvider>
    </MemoryRouter>
  )
  await waitFor(() => expect(search).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
  isAdmin = false
  units.mockResolvedValue({
    total_units: 1,
    dimensions: [
      {
        dimension: 'stress',
        si_unit: 'Pa',
        alias_of: null,
        aliases: [{ written: 'kgf/mm2', means: 'kgf/mm²' }],
        units: [{ symbol: 'MPa', factor: '1e6', offset: '0', is_si: false }],
      },
    ],
  })
})

describe('단위', () => {
  it('축과 섞이지 않고 따로 선다', async () => {
    // **축은 값을 더할 수 있고 단위는 못 고친다.** 같은 줄에 놓으면 그 차이가
    // 안 보이고, 사람이 「단위도 추가할 수 있나」 를 묻게 된다.
    await show([term()])
    expect(screen.getByRole('button', { name: '단위' })).toBeInTheDocument()
    // **제목은 안 붙인다.** 항목이 하나뿐인데 이름을 달면 「여기 더 있다」 로
    // 읽히고, 그 이름이 잘 안 붙는다 — 「고칠 수 없는 것」 은 무엇이 못 고치는지
    // (권한? 고장?)가 안 드러난다. 다른 종류라는 것은 선으로 충분하다.
    expect(screen.queryByText('고칠 수 없는 것')).not.toBeInTheDocument()
  })

  it('고르면 단위 표가 뜨고 값 목록은 물러난다', async () => {
    // 둘이 같이 뜨면 검색창이 어느 쪽을 찾는지 알 수 없다.
    const user = userEvent.setup()
    await show([term()])
    await user.click(screen.getByRole('button', { name: '단위' }))
    expect(await screen.findByText(/이 표는 화면에서 고칠 수 없습니다/)).toBeInTheDocument()
    expect(screen.queryByText('포스코')).not.toBeInTheDocument()
  })
})

describe('기준정보 보기', () => {
  it('멤버에게 고치는 길을 주지 않는다', async () => {
    await show([term()])
    expect(await screen.findByText('포스코')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '편집' })).not.toBeInTheDocument()
  })

  it('관리자에게는 고치러 가는 길을 준다', async () => {
    // **없으면 관리자도 주소를 외워야 한다.** 보고 나서 고치는 것이 이어진다.
    isAdmin = true
    await show([term()])
    expect(await screen.findByRole('link', { name: '편집' })).toHaveAttribute(
      'href',
      '/admin/vocabulary'
    )
  })

  it('감춘 값을 감추지 않고 감췄다고 적는다', async () => {
    // 목록에는 있는데 드롭다운에 안 뜨는 값이 있다. 그 이유가 화면에 없으면
    // 「내 화면만 이상한가」 가 된다.
    await show([term({ value: '옛제조사', status: 'hidden' })])
    expect(await screen.findByText('옛제조사')).toBeInTheDocument()
    expect(screen.getByText('감춤')).toBeInTheDocument()
  })

  it('몇 개 중 몇 개인지 말한다', async () => {
    // 100줄만 그리는데 그 말이 없으면 「이것이 전부」 로 읽힌다.
    await show([term()], 340)
    expect(await screen.findByText(/340개 중 1개/)).toBeInTheDocument()
  })
})
