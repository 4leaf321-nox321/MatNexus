/**
 * 카드 항목 — **어느 재료에서 무엇까지 볼 수 있나.**
 *
 * 무는 자리를 「표가 뜬다」 보다 **「재료가 많으면 요약부터」**·「요약에서 누른 자리로
 * 들어간다」·「자른 것은 말한다」·「지금 볼 수 있는 것과 시험·선언을 섞지 않는다」·
 * 「값은 표시 단위로」 에 둔다. 1만 줄을 한 장에 펴던 첫 판은 3.6 초 걸렸고 읽을 수도
 * 없었다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CardItemsTab, PAGE, SUMMARY_FROM } from '@/modules/statistics/CardItemsTab'
import type {
  CardItemColumn,
  CardItemRows,
  CardItemSummary,
} from '@/modules/statistics/analysisApi'

const cardItemSummary = vi.fn()
const cardItemRows = vi.fn()
const cardItemCell = vi.fn()

vi.mock('@/modules/statistics/analysisApi', async () => {
  const actual = await vi.importActual<typeof import('@/modules/statistics/analysisApi')>(
    '@/modules/statistics/analysisApi'
  )
  return {
    ...actual,
    analysisApi: {
      cardItemSummary: (...a: unknown[]) => cardItemSummary(...a),
      cardItemRows: (...a: unknown[]) => cardItemRows(...a),
      cardItemCell: (...a: unknown[]) => cardItemCell(...a),
    },
  }
})

function column(key: string, label: string, over: Partial<CardItemColumn> = {}): CardItemColumn {
  return {
    key,
    label,
    help: `**${label}** 설명`,
    tests: [],
    registered: true,
    published_materials: 0,
    card_materials: 0,
    deprecated_materials: 0,
    source_materials: 0,
    ...over,
  }
}

const COLUMNS = [
  column('elastic', '탄성', {
    tests: ['인장시험'],
    published_materials: 1,
    card_materials: 1,
    source_materials: 1,
  }),
  column('viscoelastic', '점탄성', { tests: ['DMA 스윕'], deprecated_materials: 1 }),
  column('hyperelastic', '초탄성'),
]

function summaryOf(total: number): CardItemSummary {
  return {
    columns: COLUMNS,
    groups: [
      {
        family: 'Metal',
        category: 'Steel',
        material_count: 40,
        card_materials: 5,
        source_only_materials: 3,
        cells: {
          elastic: { published: 1, draft: 4, deprecated: 0, source: 3 },
          viscoelastic: { published: 0, draft: 0, deprecated: 2, source: 0 },
        },
      },
    ],
    material_total: total,
    card_material_count: 5,
    source_only_count: 3,
  }
}

const ROWS: CardItemRows = {
  columns: COLUMNS,
  rows: [
    {
      material_id: 'm-secc',
      material_name: 'SECC',
      family: 'Metal',
      category: 'Steel',
      cells: {
        elastic: { state: 'published', card_count: 2, tests: true, declared: false },
        viscoelastic: { state: 'deprecated', card_count: 1, tests: false, declared: false },
      },
    },
    {
      material_id: 'm-spcc',
      material_name: 'SPCC',
      family: 'Metal',
      category: 'Steel',
      cells: { elastic: { state: 'source', card_count: 0, tests: false, declared: true } },
    },
  ],
  total: 250,
  limit: PAGE,
  offset: 0,
}

function mount(query = '') {
  return render(
    <MemoryRouter initialEntries={[`/compare?tab=card-items${query}`]}>
      <CardItemsTab />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  cardItemSummary.mockResolvedValue(summaryOf(135))
  cardItemRows.mockResolvedValue(ROWS)
  cardItemCell.mockResolvedValue({
    state: 'published',
    cards: [
      {
        id: 'c1',
        label: 'SECC 인장',
        status: 'published',
        values: [{ label: '탄성계수', value: 2.0e11, si_unit: 'Pa' }],
        row_count: 12,
      },
    ],
    tests: [{ key: 'tensile', label: '인장시험', adopted_count: 3 }],
    declared: [],
  })
})

describe('요약과 전체', () => {
  it('재료가 적으면 전체부터 — 재료군·분류가 재료 왼쪽에 선다', async () => {
    mount()
    expect(await screen.findByRole('link', { name: 'SECC' })).toBeInTheDocument()
    const heads = screen.getAllByRole('columnheader').map((one) => one.textContent)
    expect(heads.slice(0, 3)).toEqual(['재료군', '분류', '재료'])
    expect(screen.getByRole('button', { name: '전체' })).toHaveAttribute('aria-pressed', 'true')
  })

  it(`재료가 ${SUMMARY_FROM}개를 넘으면 요약부터 — 줄은 분류다`, async () => {
    cardItemSummary.mockResolvedValue(summaryOf(SUMMARY_FROM + 500))
    mount()
    expect(await screen.findByText(/재료가 많아 요약부터 엽니다/)).toBeInTheDocument()
    // 요약은 재료 줄을 안 묻는다 — 1만 줄을 받지 않는 것이 요점이다.
    expect(cardItemRows).not.toHaveBeenCalled()
    // 칸은 「카드가 있는 재료 / 분류의 재료」, 아래 줄은 그중 확정.
    const cell = screen.getByRole('button', { name: 'Metal · Steel · 탄성 재료 보기' })
    expect(cell).toHaveTextContent('5/40')
    expect(cell).toHaveTextContent('확정 1')
    // 사용 중지뿐인 칸은 「있는데 0」 이 아니라 중지로 말한다.
    expect(
      screen.getByRole('button', { name: 'Metal · Steel · 점탄성 재료 보기' })
    ).toHaveTextContent('중지 2')
  })

  it('요약의 칸을 누르면 그 분류 · 그 항목의 재료 줄로 간다', async () => {
    const user = userEvent.setup()
    mount('&view=summary')
    await user.click(await screen.findByRole('button', { name: 'Metal · Steel · 탄성 재료 보기' }))
    await waitFor(() =>
      expect(cardItemRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ family: 'Metal', category: 'Steel', item: 'elastic', offset: 0 })
      )
    )
    // **걸린 것을 보이고 풀 수 있게.**
    expect(await screen.findByText('Metal · Steel')).toBeInTheDocument()
    expect(screen.getByText(/「탄성」 있는 재료만/)).toBeInTheDocument()
  })
})

describe('전체', () => {
  it('자른 것은 말하고 다음 쪽을 묻는다', async () => {
    const user = userEvent.setup()
    mount('&view=all')
    expect(await screen.findByText(/재료 250개 중 1–2/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '다음' }))
    await waitFor(() =>
      expect(cardItemRows).toHaveBeenLastCalledWith(expect.objectContaining({ offset: PAGE }))
    )
  })

  it('빈 항목은 열을 접되 이름을 적는다', async () => {
    const user = userEvent.setup()
    mount('&view=all')
    await screen.findByRole('link', { name: 'SECC' })
    const name = '초탄성 — 이 항목이 있는 재료만 보기'
    expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    expect(screen.getByText(/카드가 없는 항목 1 — 초탄성/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '빈 열도 보기' }))
    expect(screen.getByRole('button', { name })).toBeInTheDocument()
  })

  it('시험·선언은 켜야 묻고, 무엇이 있는지 그대로 말한다', async () => {
    const user = userEvent.setup()
    mount('&view=all')
    await screen.findByRole('link', { name: 'SECC' })
    expect(cardItemRows).toHaveBeenLastCalledWith(expect.objectContaining({ withSources: false }))
    await user.click(screen.getByRole('button', { name: '시험·선언만 있는 것도 보기' }))
    await waitFor(() =>
      expect(cardItemRows).toHaveBeenLastCalledWith(expect.objectContaining({ withSources: true }))
    )
    // 「만들 수 있음」 이 아니라 **있는 것**을 — 이 재료는 선언뿐이다.
    expect(screen.getByRole('button', { name: 'SPCC · 탄성 자세히' })).toHaveTextContent(
      '선언 있음'
    )
  })

  it('확정이 앞서고 여러 장이면 장 수를 — 사용 중지뿐이면 중지', async () => {
    mount('&view=all')
    const cell = await screen.findByRole('button', { name: 'SECC · 탄성 자세히' })
    expect(cell).toHaveTextContent('확정')
    expect(cell).toHaveTextContent('2장')
    expect(screen.getByRole('button', { name: 'SECC · 점탄성 자세히' })).toHaveTextContent('중지')
  })

  it('칸을 누르면 그때 값을 받아 표시 단위로 보인다', async () => {
    const user = userEvent.setup()
    mount('&view=all')
    await user.click(await screen.findByRole('button', { name: 'SECC · 탄성 자세히' }))
    expect(cardItemCell).toHaveBeenCalledWith('m-secc', 'elastic')
    const dialog = await screen.findByRole('dialog')
    // 서버는 SI(Pa)로 준다 — **표시 단위로** 읽힌다. 설명의 `**` 는 걷는다.
    expect(await within(dialog).findByText('200000 MPa')).toBeInTheDocument()
    expect(within(dialog).getByText('탄성 설명')).toBeInTheDocument()
    expect(within(dialog).getByText('표 12줄')).toBeInTheDocument()
    expect(within(dialog).getByText('인장시험 3건')).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: '재료의 CAE 카드 열기' })).toHaveAttribute(
      'href',
      '/materials/m-secc?tab=cards'
    )
  })
})
