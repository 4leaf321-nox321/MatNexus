/**
 * 장비 파일 정의 — **처리결과 표의 열도 매핑할 수 있는가, 무엇이 열리는지 보이는가.**
 *
 * 두 가지가 조용히 틀렸다.
 *
 *   1. 매핑 표에 측정 열만 넣었다. 매핑은 **표를 안 가리고 열 이름으로** 걸리므로
 *      (`profile.py`), 처리결과 표만 다른 이름을 쓰면 그 열은 화면에서 정할 방법이
 *      없었다 — 장비가 만든 마스터커브를 가져올 때 「저장 탄성률 열이 없습니다」
 *      에서 막힌다.
 *   2. 점탄성 탭은 채널 조합으로 **자동으로** 뜬다. 그 규칙이 어디에도 안 적혀
 *      있어서, 정의를 만드는 사람은 저장하고 시험을 열어 봐야 없다는 것을 알았다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import FormatProfileEditorPage from '@/modules/tests/FormatProfileEditorPage'

const previewFormat = vi.fn()

/** 인장 종류 — **저장·손실 탄성률이 없다.** 점탄성 탭이 안 열리는 쪽 표본이다. */
const TENSILE = {
  key: 'tensile',
  label: '인장',
  abbr: 'TT',
  parser_key: null,
  description: null,
  sort_order: 10,
  is_active: true,
  channels: [
    {
      key: 'displacement',
      label: '변위',
      dimension: 'length',
      si_unit: 'm',
      is_required: true,
      sort_order: 0,
    },
    {
      key: 'force',
      label: '하중',
      dimension: 'force',
      si_unit: 'N',
      is_required: true,
      sort_order: 1,
    },
  ],
  conditions: [],
}

/** DMA 종류 — 저장·손실 탄성률이 선언돼 있다. */
const DMA = {
  ...TENSILE,
  key: 'dma_sweep',
  label: 'DMA 스윕',
  abbr: 'DMA',
  channels: [
    {
      key: 'storage_modulus',
      label: '저장 탄성률',
      dimension: 'stress',
      si_unit: 'Pa',
      is_required: true,
      sort_order: 0,
    },
    {
      key: 'loss_modulus',
      label: '손실 탄성률',
      dimension: 'stress',
      si_unit: 'Pa',
      is_required: true,
      sort_order: 1,
    },
    {
      key: 'temperature',
      label: '온도',
      dimension: 'temperature',
      si_unit: 'K',
      is_required: true,
      sort_order: 2,
    },
    {
      key: 'frequency',
      label: '주파수',
      dimension: 'frequency',
      si_unit: 'Hz',
      is_required: false,
      sort_order: 3,
    },
  ],
}

function profile(testTypeKey: string, columns: Record<string, unknown> = {}) {
  return {
    id: 'p1',
    key: 'ta_dma',
    label: 'TA DMA850',
    description: null,
    test_type_key: testTypeKey,
    priority: 10,
    is_active: true,
    is_global: true,
    owner_workspace_slug: null,
    owner_workspace_name: null,
    definition: {
      match: { extensions: ['.csv'], header_any: ['Storage Modulus'] },
      // **표 전부를 본다.** 「첫 표만」 이면 처리결과 표가 아예 안 걸린다.
      tables: { mode: 'all', include: '^Temperature', derived: '^TTS' },
      columns,
    },
  }
}

/** 측정 표와 처리결과 표가 **다른 이름**으로 저장 탄성률을 적은 파일. 실재한다. */
const PREVIEW = {
  filename: 'dma.csv',
  encoding: 'utf-8',
  delimiter: ',',
  line_count: 200,
  meta: [],
  warnings: [],
  matched_profile: null,
  tables: [
    {
      index: 0,
      name: 'Temperature Sweep - 2',
      header: ['Temperature', 'Frequency', 'Storage Modulus', 'Loss Modulus'],
      units: ['°C', 'Hz', 'MPa', 'MPa'],
      unit_symbols: ['degC', 'Hz', 'MPa', 'MPa'],
      dimensions: ['temperature', 'frequency', 'stress', 'stress'],
      row_count: 8,
      column_count: 4,
      first_line: 3,
      sample_rows: [['-40', '0.1', '1200', '80']],
    },
    {
      index: 1,
      name: 'TTS - master curve (20.0 °C)',
      header: ['Frequency', 'E-prime (master)'],
      units: ['Hz', 'MPa'],
      unit_symbols: ['Hz', 'MPa'],
      dimensions: ['frequency', 'stress'],
      row_count: 40,
      column_count: 2,
      first_line: 90,
      sample_rows: [['0.001', '900']],
    },
  ],
}

let types: unknown[] = [TENSILE, DMA]
let currentProfile = profile('tensile')

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: () => Promise.resolve(types),
    formats: () => Promise.resolve([currentProfile]),
    updateFormat: () => Promise.resolve({}),
    previewFormat: (...args: unknown[]) => previewFormat(...args),
    tryFormat: () => Promise.resolve({ curves: [], summary: [], metadata: {}, warnings: [] }),
  },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

async function open(testTypeKey = 'tensile', columns: Record<string, unknown> = {}) {
  currentProfile = profile(testTypeKey, columns)
  const view = render(
    <MemoryRouter initialEntries={['/settings/formats/ta_dma']}>
      <Routes>
        <Route path="/settings/formats/:key" element={<FormatProfileEditorPage />} />
      </Routes>
    </MemoryRouter>
  )
  await screen.findByDisplayValue('TA DMA850')
  const input = view.container.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, new File(['x'], 'dma.csv', { type: 'text/csv' }))
  await waitFor(() => expect(previewFormat).toHaveBeenCalled())
  // **열 이름은 화면에 여러 번 나온다** — 헤더 지문 칩에도 같은 글자가 뜬다.
  // 그래서 매핑 표가 그려진 것을 요약 상자로 확인한다.
  await screen.findByText('이 매핑이면 무엇이 열리나')
  return view
}

/** 매핑 표 안에서만 찾는다 — 같은 열 이름이 헤더 지문 칩에도 나온다. */
function mapping() {
  return within(screen.getByLabelText('열 매핑'))
}

/** 「이 매핑이면 무엇이 열리나」 의 한 줄 안에서만 찾는다. */
function opened(label: string) {
  const box = screen.getByText('이 매핑이면 무엇이 열리나').parentElement as HTMLElement
  const row = within(box).getByText(label).closest('div')?.parentElement as HTMLElement
  return within(row)
}

beforeEach(() => {
  previewFormat.mockReset()
  previewFormat.mockResolvedValue(PREVIEW)
  types = [TENSILE, DMA]
  window.localStorage.clear()
})

describe('처리결과 표의 열도 매핑한다', () => {
  it('기본으로는 접혀 있고 몇 개인지 말한다', async () => {
    // 원래 뺀 이유(표가 두 배로 길어진다)는 그대로 지킨다.
    await open()
    expect(screen.getByText(/처리결과 표에만 있는 열/)).toBeInTheDocument()
    expect(mapping().queryByText('E-prime (master)')).toBeNull()
  })

  it('펼치면 그 열이 나오고 처리결과라고 적힌다', async () => {
    // **이것이 없으면 정할 방법이 아예 없다** — 매핑은 열 이름으로 걸리는데
    // 그 이름이 화면에 안 나온다.
    await open()
    await userEvent.click(screen.getByRole('button', { name: '펼쳐서 매핑하기' }))
    const cell = mapping().getByText('E-prime (master)').closest('td') as HTMLElement
    expect(within(cell).getByText('처리결과')).toBeInTheDocument()
  })

  it('이미 정해 둔 열은 접혀 있어도 보인다', async () => {
    // **저장된 매핑이 화면에서 사라지면 안 된다.** 단위 경고가 떠도 어느 열인지
    // 찾을 수 없고, 지우려 해도 줄이 없다.
    await open('dma_sweep', {
      'E-prime (master)': { channel: 'storage_modulus', unit: 'MPa' },
    })
    expect(mapping().getByText('E-prime (master)')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '펼쳐서 매핑하기' })).toBeNull()
  })

  it('처리결과 열을 매핑하면 가져오기가 열린다', async () => {
    // 이 화면을 고친 이유 전부다 — 전에는 이 매핑을 할 자리가 없었다.
    await open('dma_sweep', {
      'E-prime (master)': { channel: 'storage_modulus', unit: 'MPa' },
    })
    expect(opened('장비가 만든 마스터커브 가져오기').getByText('열림')).toBeInTheDocument()
  })

  it('측정 표에도 있는 이름은 접히지 않는다', async () => {
    // `Frequency` 는 양쪽 표에 있다. 매핑하면 둘 다에 걸리므로 접을 이유가 없다.
    await open()
    expect(mapping().getByText('Frequency')).toBeInTheDocument()
  })
})

describe('무엇이 열리는지 보여 준다', () => {
  it('인장 종류면 점탄성 탭이 안 열린다고 말한다', async () => {
    // **자동으로 생기는 화면**이라, 안 적으면 만드는 사람은 저장하고 시험을
    // 열어 봐야 없다는 것을 안다.
    await open('tensile')
    expect(opened('점탄성 탭').getByText('안 열림')).toBeInTheDocument()
  })

  it('무엇이 빠졌는지 채널 이름으로 적는다', async () => {
    await open('tensile')
    expect(opened('점탄성 탭').getByText(/storage_modulus/)).toBeInTheDocument()
    expect(opened('점탄성 탭').getByText(/loss_modulus/)).toBeInTheDocument()
  })

  it('DMA 종류면 점탄성 탭이 열린다', async () => {
    await open('dma_sweep')
    expect(opened('점탄성 탭').getByText('열림')).toBeInTheDocument()
  })

  it('겹치기는 측정 표의 열로 판단한다', async () => {
    // 측정 표에 온도·주파수·저장 탄성률이 다 있다 — 매핑을 안 해도 영문 표기가
    // 그대로 키가 되므로(`slug`) 열린다.
    await open('dma_sweep')
    expect(opened('겹치기 (마스터커브 만들기)').getByText('열림')).toBeInTheDocument()
  })

  it('가져오기는 처리결과 표의 열로 판단한다', async () => {
    // **여기가 이 화면의 요점이다.** 측정 표에는 저장 탄성률이 있지만 처리결과
    // 표는 다른 이름을 적었다 — 그래서 가져오기는 안 열린다.
    await open('dma_sweep')
    const row = opened('장비가 만든 마스터커브 가져오기')
    expect(row.getByText('안 열림')).toBeInTheDocument()
    expect(row.getByText(/storage_modulus/)).toBeInTheDocument()
    // **두 표에 다 있는 열은 양쪽으로 센다.** `Frequency` 는 측정 표에도 있는데,
    // 이름으로 덮어쓰면 처리결과 쪽에서 사라져 없는 문제를 만들어 낸다.
    expect(row.queryByText(/angular_frequency/)).toBeNull()
  })
})
