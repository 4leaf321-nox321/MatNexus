/**
 * 표로 시험 넣기.
 *
 * **곡선이 없는 시험도 데이터다.** 기존 표에 쌓인 것을 못 가져오면 사용자가
 * 옮겨오지 않는다 — 도입 성패가 여기서 갈린다.
 *
 * 여기서 지키는 것은 둘이다.
 *
 *   미리보기는 아무것도 안 쓴다        누르기 전에 무엇이 들어갈지 안다
 *   시편을 만드는지 보인다             켜 두면 표가 시편을 늘린다
 *   종류를 고를 수 있다                인장 고정이던 때 피로 · 크리프 요약값을 넣을 길이 없었다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SummaryImportDialog, defaultColumns } from '@/modules/tests/SummaryImportDialog'

const importSummaries = vi.fn()

function field(key: string, label: string, siUnit: string, dimension: string, required: boolean) {
  return {
    key,
    label,
    si_unit: siUnit,
    dimension,
    is_required: required,
    value_type: 'number',
    choices: null,
    sort_order: 0,
  }
}

const TYPES = [
  { key: 'tensile', label: '인장시험', is_active: true, conditions: [] },
  {
    key: 'fatigue',
    label: '피로',
    is_active: true,
    conditions: [
      field('stress_amplitude', '응력 진폭', 'Pa', 'stress', true),
      field('stress_ratio', '응력비 R', '1', 'dimensionless', false),
    ],
  },
  {
    key: 'creep',
    label: '크리프',
    is_active: true,
    conditions: [
      field('applied_stress', '가한 응력', 'Pa', 'stress', true),
      field('temperature', '시험 온도', 'K', 'temperature', true),
    ],
  },
]

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    importSummaries: (...args: unknown[]) => importSummaries(...args),
    types: () => Promise.resolve(TYPES),
  },
}))

const ANSWER = {
  created: 1,
  existing: 0,
  skipped: 0,
  rejected: 0,
  specimens_created: 1,
  items: [
    {
      input: 'MD-2',
      status: 'new',
      specimen: 'SECC_1_MD_2',
      creates_specimen: true,
      run: null,
      conditions: {},
      summaries: {},
      reason: null,
      warnings: [],
    },
  ],
}

/** 창을 열고 **종류 목록이 그려질 때까지** 기다린다 — 늦게 오는 목록이 시험 뒤에 화면을 바꾸지 않게. */
async function show() {
  const onDone = vi.fn()
  render(
    <SummaryImportDialog
      sampleId="sample-1"
      sampleName="SECC_1"
      onClose={() => {}}
      onDone={onDone}
    />
  )
  await screen.findByLabelText('시험 종류')
  return onDone
}

/** 표에 한 줄 적는다. 첫 열이 시편이다. */
async function type(user: ReturnType<typeof userEvent.setup>, value: string) {
  await user.type(screen.getByLabelText('1번 줄 시편'), value)
}

beforeEach(() => {
  vi.clearAllMocks()
  importSummaries.mockResolvedValue(ANSWER)
})

describe('표로 시험 입력', () => {
  it('곡선이 없다는 것을 먼저 말한다', async () => {
    // **모자란 데이터라는 뜻이 아니다** — 낼 수 있는 물성의 범위가 다를 뿐이다.
    await show()
    expect(screen.getByText(/곡선은/)).toBeInTheDocument()
  })

  it('요약값 열을 사람이 정한다', async () => {
    // **표마다 열이 다르고 미리 알 방법이 없다.**
    const user = userEvent.setup()
    await show()
    await user.clear(screen.getByLabelText('요약값 열'))
    await user.type(screen.getByLabelText('요약값 열'), 'n값')

    expect(screen.getByLabelText('1번 줄 n값')).toBeInTheDocument()
  })

  it('미리 보기는 쓰지 않는다고 서버에 말한다', async () => {
    const user = userEvent.setup()
    await show()
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '미리보기' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][1]).toMatchObject({ dry: true })
  })

  it('없는 시편 만들기는 기본이 꺼짐이다', async () => {
    // **오타 하나가 유령 시편을 만든다.**
    const user = userEvent.setup()
    await show()
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '입력' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][1]).toMatchObject({
      dry: false,
      createMissing: false,
    })
  })

  it('켜면 그렇게 보낸다', async () => {
    const user = userEvent.setup()
    await show()
    await user.click(screen.getByRole('checkbox'))
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '입력' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][1]).toMatchObject({ createMissing: true })
  })

  it('시편까지 만드는 줄을 표시한다', async () => {
    // **켜 두면 표가 시편을 늘린다** — 그 사실이 줄마다 보여야 한다.
    const user = userEvent.setup()
    await show()
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '미리보기' }))

    expect(await screen.findByText('시편도 만듦')).toBeInTheDocument()
  })

  it('빈 표로는 못 보낸다', async () => {
    await show()
    expect(screen.getByRole('button', { name: '입력' })).toBeDisabled()
  })
})

describe('시험 종류', () => {
  it('처음은 인장시험이고 옛 요약표의 열 그대로다', async () => {
    await show()
    expect(screen.getByLabelText('시험 종류')).toHaveValue('tensile')
    expect(screen.getByLabelText('요약값 열')).toHaveValue(
      '항복강도 (MPa), 인장강도 (MPa), 연신율 (%)'
    )
  })

  it('피로를 고르면 필수 조건과 묶음이 읽는 키로 열이 바뀐다', async () => {
    // **열 이름이 곧 저장 키다** — cycles_to_failure 가 아니면 S-N 묶음이 그 시험을 못 본다.
    const user = userEvent.setup()
    await show()
    await user.selectOptions(screen.getByLabelText('시험 종류'), 'fatigue')

    expect(screen.getByLabelText('요약값 열')).toHaveValue(
      '응력 진폭 (MPa), cycles_to_failure, runout, 응력비 R'
    )
    expect(screen.getByRole('heading', { name: '표로 피로 입력' })).toBeInTheDocument()
  })

  it('고른 종류로 보낸다', async () => {
    const user = userEvent.setup()
    await show()
    await user.selectOptions(screen.getByLabelText('시험 종류'), 'creep')
    expect(screen.getByLabelText('요약값 열')).toHaveValue(
      '가한 응력 (MPa), 시험 온도 (°C), min_creep_rate (1/s)'
    )
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '미리보기' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][0]).toMatchObject({ test_type: 'creep' })
  })
})

describe('굽힘 요약값 열', () => {
  it('묶음이 읽는 굽힘 탄성률 · 강도 키를 깐다', () => {
    // 보고서만 있는 굽힘 시험(칩 · 모듈)도 「굽힘 등가 탄성률」 묶음에 들어가야 한다 — 열
    // 이름이 곧 저장 키라서 flexural_modulus 가 아니면 묶음이 못 본다.
    const flexural = {
      key: 'flexural',
      conditions: [field('temperature', '시험 온도', 'K', 'temperature', false)],
    } as unknown as Parameters<typeof defaultColumns>[0]
    expect(defaultColumns(flexural)).toBe(
      'flexural_modulus (MPa), flexural_strength (MPa), 시험 온도 (°C)'
    )
  })
})
