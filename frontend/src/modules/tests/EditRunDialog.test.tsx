/**
 * 시험 고치기 — **저장된 SI 를 화면 단위로 보여 주고, 화면 단위와 함께 돌려보낸다.**
 *
 * 값만 갈아 끼우는 편집이 6만 배 사고의 자리였다(업로드에서 실제로 났다). 편집도
 * 등록과 같은 규칙 — 조건은 단위를 붙여 보낸다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EditRunDialog } from '@/modules/tests/EditRunDialog'
import type { TestRunDetail, TestType } from '@/modules/tests/api'

const update = vi.fn()
const replaceSource = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    update: (...args: unknown[]) => update(...args),
    replaceSource: (...args: unknown[]) => replaceSource(...args),
  },
}))
vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: ({ label, value }: { label: string; value: string }) => (
    <label>
      {label}
      <input readOnly aria-label={label} value={value} />
    </label>
  ),
}))

const TYPE = {
  key: 'tensile',
  label: '인장',
  conditions: [
    {
      key: 'speed_elastic',
      label: '탄성 구간 속도',
      value_type: 'number',
      dimension: 'velocity',
      si_unit: 'm/s',
      choices: null,
      is_required: false,
    },
    {
      key: 'clamp',
      label: '지그',
      value_type: 'text',
      dimension: null,
      si_unit: null,
      choices: null,
      is_required: false,
    },
  ],
} as unknown as TestType

const RUN = {
  id: 'r1',
  record_name: 'SECC_-_1.0__01__MD_01__TEN_01',
  conditions: { speed_elastic: 10 / 60000 },
  tested_at: null,
  operator: '김시험',
  instrument: null,
  division: null,
  note: null,
  source_filename: 'a.tra',
  source_history: [],
  result_count: 2,
} as unknown as TestRunDetail

beforeEach(() => {
  update.mockReset()
  update.mockResolvedValue(RUN)
  replaceSource.mockReset()
  replaceSource.mockResolvedValue({ status: 'queued', message: '바꿨습니다', stale_results: 2 })
})

describe('EditRunDialog', () => {
  it('저장된 m/s 를 mm/min 으로 보여 주고, 고친 값을 단위와 함께 보낸다', async () => {
    const user = userEvent.setup()
    const onDone = vi.fn()
    render(<EditRunDialog run={RUN} testType={TYPE} onClose={vi.fn()} onDone={onDone} />)

    const speed = screen.getByLabelText(/탄성 구간 속도 \(mm\/min\)/)
    expect(speed).toHaveValue(10)
    await user.clear(speed)
    await user.type(speed, '5')
    await user.type(screen.getByLabelText('지그'), '3 Point Bending Clamp')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [id, payload] = update.mock.calls[0] as [string, Record<string, unknown>]
    expect(id).toBe('r1')
    expect(payload).toMatchObject({
      operator: '김시험',
      conditions: { speed_elastic: 5, clamp: '3 Point Bending Clamp' },
      condition_units: { speed_elastic: 'mm/min' },
    })
    expect(onDone).toHaveBeenCalled()
  })

  it('원본을 바꾸면 옛 결과가 옛 원본의 것이 된다고 먼저 말한다', async () => {
    render(<EditRunDialog run={RUN} testType={TYPE} onClose={vi.fn()} onDone={vi.fn()} />)
    expect(screen.getByText(/처리 결과 2건은 옛 원본의 것이 됩니다/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /원본 교체 후 재파싱/ })).toBeDisabled()
  })
})
