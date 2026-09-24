/**
 * 시험 등록 창 — **의뢰 항목에서 열 때**(시료가 정해진 채). 그 시료의 시편 중에서 고르거나
 * 하나 만들고, 종류·조건이 채워진 채 뜨고, 등록되면 시험을 돌려줘 항목이 그 자리에서 붙인다.
 * 다른 시료의 시편은 고를 수 없다 — 의뢰가 재지도 않은 것을 잰 것으로 적으면 안 된다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UploadDialog } from '@/modules/tests/UploadDialog'

const upload = vi.fn()
const specimens = vi.fn()
const createSpecimen = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: () =>
      Promise.resolve([
        {
          key: 'tensile',
          label: '인장시험',
          extensions: [],
          parser_key: null,
          max_upload_bytes_effective: 1024 * 1024,
          channels: [],
          conditions: [
            {
              key: 'temperature',
              label: '시험 온도',
              value_type: 'number',
              dimension: 'temperature',
              si_unit: 'K',
              choices: null,
              is_required: false,
              sort_order: 0,
              canonical_key: 'temperature',
            },
          ],
        },
      ]),
    upload: (...args: unknown[]) => upload(...args),
  },
}))

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    specimens: (...args: unknown[]) => specimens(...args),
    createSpecimen: (...args: unknown[]) => createSpecimen(...args),
  },
}))

vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: () => null,
}))

const SPECIMEN = { id: 'sp1', record_name: 'SECC_S1_MD_01', orientation: 'MD' }

beforeEach(() => {
  vi.clearAllMocks()
  specimens.mockResolvedValue([SPECIMEN])
  createSpecimen.mockResolvedValue({ id: 'sp2', record_name: 'SECC_S1_TD_01', orientation: 'TD' })
  upload.mockResolvedValue({ id: 'run1', record_name: 'SECC_S1_MD_01__TEN_01' })
})

describe('의뢰 항목에서 열 때', () => {
  it('그 시료의 시편만 고르고, 조건이 채워진 채, 등록되면 시험을 돌려준다', async () => {
    const user = userEvent.setup()
    const onUploaded = vi.fn()
    render(
      <UploadDialog
        open
        sampleId="s1"
        presetTestType="tensile"
        presetConditions={{ temperature: '80' }}
        onClose={() => {}}
        onDone={() => {}}
        onUploaded={onUploaded}
      />
    )
    const select = await screen.findByLabelText('시편 (이 의뢰의 시료)')
    // 고르개는 시편 목록보다 먼저 선다 — 목록이 오기 전에 고르면 「없는 값」 이다.
    await within(select).findByRole('option', { name: /SECC_S1_MD_01/ })
    await user.selectOptions(select, 'sp1')
    expect(specimens).toHaveBeenCalledWith('s1')
    // 조건이 채워진 채 뜬다 — 의뢰 항목의 80 °C.
    expect(screen.getByLabelText(/시험 온도/)).toHaveValue(80)

    // 대화상자는 포털에 그려진다 — 라벨로 잡는다.
    await user.upload(screen.getByLabelText('원본 파일'), new File(['x'], 'run.tra'))
    await user.click(screen.getByRole('button', { name: '업로드' }))
    await waitFor(() => expect(upload).toHaveBeenCalled())
    const [payload] = upload.mock.calls[0] as [Record<string, unknown>]
    expect(payload.specimenId).toBe('sp1')
    expect(payload.testType).toBe('tensile')
    expect(payload.conditions).toEqual({ temperature: 80 })
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith({ id: 'run1', record_name: 'SECC_S1_MD_01__TEN_01' }))
  })

  it('시편이 없으면 그 자리에서 하나 만들어 고른다', async () => {
    specimens.mockResolvedValue([])
    const user = userEvent.setup()
    render(
      <UploadDialog open sampleId="s1" presetTestType="tensile" onClose={() => {}} onDone={() => {}} />
    )
    expect(await screen.findByText(/시편이 없습니다/)).toBeInTheDocument()
    await user.clear(screen.getByLabelText('새 시편 방향'))
    await user.type(screen.getByLabelText('새 시편 방향'), 'td')
    await user.click(screen.getByRole('button', { name: /새 시편/ }))
    await waitFor(() =>
      expect(createSpecimen).toHaveBeenCalledWith('s1', expect.objectContaining({ orientation: 'TD' }))
    )
  })
})
