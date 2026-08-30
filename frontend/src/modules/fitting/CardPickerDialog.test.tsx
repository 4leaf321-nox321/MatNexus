/**
 * 미리보기 카드 찾기 — **무엇을 고르는지 알아볼 수 있는가.**
 *
 * 드롭다운이 최근 20장만 보여 주므로 이 다이얼로그가 나머지를 맡는다. 그런데
 * 카드 이름은 사람이 지은 것이라(「내보내기 시험」) **어느 재료의 무슨 물성인지
 * 안 들어 있다** — 표가 재료·방향·든 물성을 보이지 않으면 목록만 길어진다.
 *
 * 무는 자리 셋:
 *
 *   1. **재료와 물성이 보인다.** 카드 이름만으로는 못 고른다.
 *   2. **점 수가 보인다.** 표를 쓰는 정의에 점 없는 카드를 고르면 미리보기가 빈
 *      표를 내는데, 정의 탓인지 카드 탓인지 화면에 안 나온다.
 *   3. **몇 장 중 몇 장인지 말한다.** 50장만 받으므로, 그 말이 없으면 찾던 카드가
 *      없을 때 「없다」 인지 「안 왔다」 인지 알 수 없다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CardPickerDialog } from '@/modules/fitting/CardPickerDialog'

const cards = vi.fn()

vi.mock('@/modules/fitting/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/fitting/api')>('@/modules/fitting/api')
  return {
    ...actual,
    fittingApi: { ...actual.fittingApi, cards: (...a: unknown[]) => cards(...a) },
  }
})

const CARD = {
  id: 'c1',
  material_name: 'SECC_1.0',
  orientation: 'MD',
  label: '내보내기 시험',
  blocks: { elastic: {}, table: {} },
  point_count: 12,
}

const BARE = {
  id: 'c2',
  material_name: 'PP_TALC20',
  orientation: null,
  label: '선언 물성',
  blocks: {},
  point_count: 0,
}

const SPECS = [
  { key: 'elastic', label: '탄성', count: 0 },
  { key: 'table', label: '소성 표', count: 0 },
]

function show(over: Partial<Parameters<typeof CardPickerDialog>[0]> = {}) {
  render(
    <CardPickerDialog
      open
      onOpenChange={() => {}}
      onPick={() => {}}
      specs={SPECS as never}
      {...over}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  cards.mockResolvedValue({ items: [CARD, BARE], total: 2 })
})

describe('무엇을 고르는지', () => {
  it('재료와 방향이 보인다 — 카드 이름만으로는 못 고른다', async () => {
    show()
    expect(await screen.findByText('SECC_1.0')).toBeInTheDocument()
    expect(screen.getByText(/· MD/)).toBeInTheDocument()
    // 카드가 지은 이름도 함께 — 같은 재료의 카드가 여럿일 수 있다.
    expect(screen.getByText('내보내기 시험')).toBeInTheDocument()
  })

  it('든 물성을 사람이 읽는 말로 보인다', async () => {
    // **화면이 `elastic`·`table` 을 몰라야 한다** — 레지스트리가 이름을 안다.
    show()
    expect(await screen.findByText('탄성')).toBeInTheDocument()
    expect(screen.getByText('소성 표')).toBeInTheDocument()
  })

  it('값이 없는 카드는 그렇다고 말한다', async () => {
    show()
    expect(await screen.findByText('값 없음')).toBeInTheDocument()
  })

  it('점 수를 보인다', async () => {
    show()
    const row = (await screen.findByText('SECC_1.0')).closest('tr') as HTMLElement
    expect(within(row).getByText('12')).toBeInTheDocument()
    const bare = (screen.getByText('PP_TALC20').closest('tr')) as HTMLElement
    expect(within(bare).getByText('—')).toBeInTheDocument()
  })
})

describe('찾기', () => {
  it('적은 대로 서버에 물어본다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText('SECC_1.0')
    await user.type(screen.getByLabelText('카드 찾기'), 'PP')
    await waitFor(() =>
      expect(cards).toHaveBeenCalledWith(expect.objectContaining({ q: 'PP' }))
    )
  })

  it('없으면 무엇으로 찾았는지 함께 말한다', async () => {
    cards.mockResolvedValue({ items: [], total: 0 })
    const user = userEvent.setup()
    show()
    await user.type(screen.getByLabelText('카드 찾기'), 'zzz')
    expect(await screen.findByText(/'zzz' 로 찾은 카드가 없습니다/)).toBeInTheDocument()
  })

  it('카드가 하나도 없으면 그렇다고 말한다', async () => {
    cards.mockResolvedValue({ items: [], total: 0 })
    show()
    expect(await screen.findByText(/아직 물성 카드가 없습니다/)).toBeInTheDocument()
  })

  it('다 안 보여 줬으면 그 사실을 말한다', async () => {
    // **없는 것과 안 온 것은 다르다.** 안 말하면 찾던 카드가 없을 때 사람은
    // 그 카드가 지워진 줄 안다.
    cards.mockResolvedValue({ items: [CARD], total: 90 })
    show()
    expect(await screen.findByText(/90장 중 1장/)).toBeInTheDocument()
  })
})

describe('고르기', () => {
  it('고르면 그 카드를 넘기고 닫는다', async () => {
    const onPick = vi.fn()
    const onOpenChange = vi.fn()
    const user = userEvent.setup()
    show({ onPick, onOpenChange })
    await screen.findByText('SECC_1.0')

    const row = screen.getByText('SECC_1.0').closest('tr') as HTMLElement
    await user.click(within(row).getByRole('button', { name: '고르기' }))
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 'c1' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('지금 고른 카드가 어느 줄인지 보인다', async () => {
    show({ current: 'c1' })
    const row = (await screen.findByText('SECC_1.0')).closest('tr') as HTMLElement
    expect(within(row).getByRole('button', { name: '고른 것' })).toBeInTheDocument()
  })
})
