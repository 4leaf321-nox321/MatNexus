/**
 * 해석용 물성 정의 편집기 — **값을 고르고, 카드에 든 것을 보고, 블록에서 출발한다.**
 *
 * 전에는 `elastic.youngs_modulus` 를 손으로 적었고, 고른 카드에 무엇이 있는지는
 * 미리보기의 「없는 값」 으로만 드러났다(2026-09-05). 이제 세 길이 있다:
 *
 *   칸의 「고르기」          블록 선언에서 값을 고른다 — 이 카드에 없는 것은 그렇다고 적힌다
 *   「이 카드에 든 것」       카드가 실제로 든 값·표. 「넣기」 가 칸을 더한다
 *   「블록으로 줄 추가」      블록 하나로 값 줄·표 줄 초안
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ExportProfileEditorPage from '@/modules/fitting/ExportProfileEditorPage'

const cards = vi.fn()
const blocks = vi.fn()
const deckKeys = vi.fn()
const previewDeck = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    exportProfiles: () => Promise.resolve([]),
    cards: (...args: unknown[]) => cards(...args),
    blocks: () => blocks(),
    deckKeys: (...args: unknown[]) => deckKeys(...args),
    previewDeck: (...args: unknown[]) => previewDeck(...args),
    unitSystems: () =>
      Promise.resolve([
        { key: 'si', label: 'SI (kg · m · s · Pa)', is_default: false },
        { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)', is_default: true },
      ]),
    scanDeck: () => Promise.resolve({ lines: [], notes: [] }),
    createExportProfile: () => Promise.resolve({}),
    saveExportProfile: () => Promise.resolve({}),
  },
}))
vi.mock('@/modules/fitting/CardPickerDialog', () => ({ CardPickerDialog: () => null }))

const SPECS = [
  {
    key: 'elastic',
    label: '탄성',
    help: '',
    order: 10,
    in_deck: true,
    produces: [
      { key: 'youngs_modulus', label: '탄성계수', si_unit: 'Pa', help: null },
      { key: 'poisson_ratio', label: '푸아송비', si_unit: '1', help: null },
      { key: 'density', label: '밀도', si_unit: 'kg/m3', help: null },
    ],
    rows: [],
    curve: null,
  },
  {
    key: 'viscoelastic',
    label: '점탄성',
    help: '',
    order: 40,
    in_deck: true,
    produces: [{ key: 'instantaneous_pa', label: '순간 탄성률', si_unit: 'Pa', help: null }],
    rows: [
      { key: 'relaxation_time_s', label: '완화시간 τᵢ', si_unit: 's', help: null },
      { key: 'relative_modulus', label: '상대 탄성률 gᵢ', si_unit: '1', help: null },
    ],
    curve: null,
  },
  {
    key: 'table',
    label: '소성 표',
    help: '',
    order: 30,
    in_deck: true,
    produces: [],
    rows: [
      { key: 'plastic_strain', label: '진소성변형률', si_unit: '1', help: null },
      { key: 'true_stress', label: '진응력', si_unit: 'Pa', help: null },
    ],
    curve: ['plastic_strain', 'true_stress'],
  },
]

const CARD = {
  id: 'c1',
  material_id: 'm1',
  material_name: 'SECC_MDOI_1.0',
  test_type_key: 'dma_sweep',
  orientation: 'NA',
  label: 'Prony 카드',
  status: 'draft',
  source: { sample_count: 1 },
  blocks: { elastic: { values: {} }, viscoelastic: { values: {}, rows: [] } },
  available_formats: [],
  problem: null,
  point_count: 0,
  note: null,
  owner_workspace_name: null,
  is_global: false,
  published_at: null,
  created_at: '2026-09-05T00:00:00Z',
}

const KEYS = {
  card_id: 'c1',
  values: [
    {
      path: 'elastic.youngs_modulus',
      block: 'elastic',
      block_label: '탄성',
      key: 'youngs_modulus',
      label: '탄성계수',
      si_unit: 'Pa',
      value: 2.05e11,
    },
    {
      path: 'viscoelastic.instantaneous_pa',
      block: 'viscoelastic',
      block_label: '점탄성',
      key: 'instantaneous_pa',
      label: '순간 탄성률',
      si_unit: 'Pa',
      value: 2.065e11,
    },
  ],
  tables: [
    {
      block: 'viscoelastic',
      block_label: '점탄성',
      row_count: 5,
      columns: [
        { key: 'relaxation_time_s', label: '완화시간 τᵢ', si_unit: 's', help: null },
        { key: 'relative_modulus', label: '상대 탄성률 gᵢ', si_unit: '1', help: null },
      ],
    },
  ],
}

function page() {
  render(
    <MemoryRouter initialEntries={['/settings/export-profiles/new']}>
      <Routes>
        <Route path="/settings/export-profiles/new" element={<ExportProfileEditorPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  cards.mockResolvedValue({ total: 1, limit: 20, offset: 0, items: [CARD] })
  blocks.mockResolvedValue(SPECS)
  deckKeys.mockResolvedValue(KEYS)
  previewDeck.mockResolvedValue({ text: '*MATERIAL', error: null, missing: [], notes: [] })
})

describe('값을 고른다', () => {
  it('칸의 「고르기」 가 블록 선언의 값을 보이고, 고르면 블록.값이 채워진다', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '1번 묶음에 값 줄' }))
    await userEvent.click(screen.getByRole('button', { name: '2번 줄 1번 칸 고르기' }))
    await userEvent.click(await screen.findByRole('button', { name: /푸아송비 elastic.poisson_ratio/ }))
    expect(screen.getByLabelText('2번 줄 1번 칸')).toHaveValue('elastic.poisson_ratio')
  })

  it('이 카드에 없는 값은 그렇다고 적는다', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '1번 묶음에 값 줄' }))
    await userEvent.click(screen.getByRole('button', { name: '2번 줄 1번 칸 고르기' }))
    const density = await screen.findByRole('button', { name: /밀도 elastic.density/ })
    expect(density).toHaveTextContent('이 카드엔 없음')
    expect(screen.getByRole('button', { name: /탄성계수 elastic.youngs_modulus/ })).not.toHaveTextContent(
      '이 카드엔 없음'
    )
  })
})

describe('이 카드에 든 것', () => {
  it('값과 표를 보이고, 「넣기」 가 마지막 묶음의 값 줄에 칸을 더한다', async () => {
    page()
    const box = within(await screen.findByLabelText('이 카드에 든 것'))
    expect(box.getByText('탄성계수')).toBeInTheDocument()
    expect(box.getByText(/점탄성 표 · 5행/)).toBeInTheDocument()
    await waitFor(() => expect(deckKeys).toHaveBeenCalledWith('c1'))

    // 값 줄이 없으면 하나 만들어 넣는다.
    await userEvent.click(box.getByRole('button', { name: '순간 탄성률 넣기' }))
    expect(screen.getByLabelText('2번 줄 1번 칸')).toHaveValue('viscoelastic.instantaneous_pa')
    // 있으면 그 줄에 칸을 더한다.
    await userEvent.click(box.getByRole('button', { name: '탄성계수 넣기' }))
    expect(screen.getByLabelText('2번 줄 2번 칸')).toHaveValue('elastic.youngs_modulus')
  })

  it('「표 줄 추가」 가 열 전부를 든 표 줄을 만든다 — Prony 계수는 이렇게 받는다', async () => {
    page()
    const box = within(await screen.findByLabelText('이 카드에 든 것'))
    await userEvent.click(box.getByRole('button', { name: '점탄성 표 줄 추가' }))
    expect(screen.getByLabelText('2번 줄 표 이름')).toHaveTextContent('점탄성')
    expect(screen.getByLabelText('2번 줄 1번 칸')).toHaveValue('relaxation_time_s')
    expect(screen.getByLabelText('2번 줄 2번 칸')).toHaveValue('relative_modulus')
    // 점 곡선인지는 블록 선언이 말한다 — Prony 표는 아니라 x·y 를 안 건다.
    expect(screen.getByLabelText('2번 줄 x 열')).toHaveValue('')
  })
})

describe('식 칸과 글자 줄', () => {
  it('값 칸을 「계산」 으로 식으로 바꾸고, 고른 값은 식에 끼워 넣는다', async () => {
    page()
    const box = within(await screen.findByLabelText('이 카드에 든 것'))
    await userEvent.click(box.getByRole('button', { name: '탄성계수 넣기' }))
    expect(screen.getByLabelText('2번 줄 1번 칸')).toHaveValue('elastic.youngs_modulus')
    await userEvent.click(screen.getByLabelText('2번 줄 1번 칸 식으로'))
    const cell = screen.getByLabelText('2번 줄 1번 칸')
    expect(cell).toHaveValue('elastic.youngs_modulus')
    await userEvent.type(cell, ' / 1000')
    // 미리보기가 식을 그대로 보낸다 — 계산은 서버가 한다.
    await waitFor(() => {
      const sent = previewDeck.mock.calls.at(-1)?.[0] as { lines: Record<string, unknown>[] }
      expect(sent.lines[1]).toEqual({
        fields: [{ expr: 'elastic.youngs_modulus / 1000', format: 'free' }],
      })
    })
    // 고르기는 값을 덮지 않고 식에 덧붙인다.
    await userEvent.click(screen.getByLabelText('2번 줄 1번 칸 고르기'))
    await userEvent.click(await screen.findByLabelText('순간 탄성률 viscoelastic.instantaneous_pa'))
    expect(screen.getByLabelText('2번 줄 1번 칸')).toHaveValue(
      'elastic.youngs_modulus / 1000 viscoelastic.instantaneous_pa'
    )
  })

  it('글자 줄은 묶음 안에 그대로 나갈 글자로 저장된다', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '1번 묶음에 글자 줄' }))
    await userEvent.type(screen.getByLabelText('2번 줄 글자'), '1, 0, 0')
    await waitFor(() => {
      const sent = previewDeck.mock.calls.at(-1)?.[0] as { lines: Record<string, unknown>[] }
      expect(sent.lines[1]).toEqual({ text: '1, 0, 0', plain: true })
    })
    // 새 묶음이 아니라 1번 묶음의 몸이다.
    expect(screen.queryByLabelText('2번 묶음 키워드')).toBeNull()
  })
})

describe('물성 묶음 추가', () => {
  it('블록 하나로 키워드·값 줄·표 줄 묶음이 서고, 첫 값이 조건이 된다', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '물성 묶음 추가' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.selectOptions(within(dialog).getByLabelText('블록'), 'viscoelastic')
    await userEvent.type(within(dialog).getByLabelText('묶음 키워드'), '*VISCOELASTIC')
    await userEvent.click(within(dialog).getByRole('button', { name: '추가' }))

    expect(screen.getByLabelText('2번 묶음 키워드')).toHaveValue('*VISCOELASTIC')
    expect(screen.getByLabelText('3번 줄 1번 칸')).toHaveValue('viscoelastic.instantaneous_pa')
    expect(screen.getByLabelText('4번 줄 표 이름')).toHaveTextContent('점탄성')
    expect(screen.getByLabelText('4번 줄 1번 칸')).toHaveValue('relaxation_time_s')
    // 값이 없으면 이 묶음을 뺀다 — 첫 값을 조건으로.
    expect(screen.getByLabelText('2번 묶음 조건')).toHaveValue('viscoelastic.instantaneous_pa')
  })

  it('점 곡선으로 선언된 표는 x·y 가 걸린다 — 소성 표', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '물성 묶음 추가' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.selectOptions(within(dialog).getByLabelText('블록'), 'table')
    await userEvent.type(within(dialog).getByLabelText('묶음 키워드'), '*PLASTIC')
    await userEvent.click(within(dialog).getByRole('button', { name: '추가' }))
    expect(screen.getByLabelText('3번 줄 x 열')).toHaveValue('plastic_strain')
    expect(screen.getByLabelText('3번 줄 y 열')).toHaveValue('true_stress')
  })
})

describe('조건은 묶음에 한 번', () => {
  it('값을 고르고 있을 때/없을 때를 뒤집는다', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '1번 묶음 조건 값 고르기' }))
    await userEvent.click(await screen.findByRole('button', { name: /밀도 elastic.density/ }))
    expect(screen.getByLabelText('1번 묶음 조건')).toHaveValue('elastic.density')
    await userEvent.click(screen.getByRole('button', { name: '있을 때' }))
    expect(screen.getByLabelText('1번 묶음 조건')).toHaveValue('missing:elastic.density')
  })
})

describe('단위계', () => {
  it('미리보기는 서버가 기본이라고 말한 계로 그린다 — 화면과 같은 mm·N·tonne', async () => {
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await waitFor(() => expect(previewDeck).toHaveBeenCalled())
    expect(previewDeck.mock.calls.at(-1)?.[2]).toBe('mm_n_tonne')
    expect(screen.getByLabelText('덱 단위계')).toHaveTextContent('mm · N · tonne')
  })
})

describe('미리보기 줄 잇기', () => {
  it('묶음에 마우스를 올리면 그 묶음이 만든 줄이 강조된다', async () => {
    previewDeck.mockResolvedValue({
      text: ['*MATERIAL', '*ELASTIC', '2.0E11, 0.3', ''].join('\n'),
      error: null,
      missing: [],
      notes: [],
      // 정의 1줄(키워드) → 덱 0~1행, 정의 2줄(값) → 덱 1~3행 (여기서는 한 묶음이다)
      spans: [
        [0, 0, 1],
        [1, 1, 3],
      ],
    })
    page()
    await screen.findByLabelText('이 카드에 든 것')
    await userEvent.click(screen.getByRole('button', { name: '1번 묶음에 값 줄' }))
    await waitFor(() => expect(previewDeck).toHaveBeenCalled())
    await screen.findByText('*ELASTIC')
    await userEvent.hover(screen.getByLabelText('1번 묶음'))
    const pre = screen.getByLabelText('덱 미리보기')
    const marked = [...pre.querySelectorAll('span')].filter((one) =>
      one.className.includes('bg-amber')
    )
    expect(marked.map((one) => one.textContent)).toEqual(['*MATERIAL', '*ELASTIC', '2.0E11, 0.3'])
  })
})
