/**
 * 일괄 등록이 **측정 의뢰의 항목에서 시작할 때**(2026-10-03).
 *
 * 의뢰 상세의 「여러 파일 한꺼번에」 가 `?material=&sample=&commission=&item=` 으로 보낸다.
 * 종류 · 조건은 항목에서 채우고, 올린 시험은 그 항목에 붙인다. 붙이기가 조용히 빠지면 의뢰의
 * 진행률이 그대로라 사람은 의뢰 화면으로 돌아가 한 건씩 다시 붙여야 한다 — 막히면 올린 것은
 * 남기고 그 줄에 이유를 적는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BatchUploadPage from '@/modules/tests/BatchUploadPage'

const upload = vi.fn()
const linkRun = vi.fn()
const createSpecimen = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: () =>
      Promise.resolve([
        {
          key: 'tensile',
          label: '인장시험',
          extensions: ['.tra'],
          profile_extensions: [],
          parser_key: null,
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
            },
          ],
        },
      ]),
    detectType: () => Promise.resolve({ test_type_key: null, reason: '모르는 형식' }),
    upload: (...args: unknown[]) => upload(...args),
  },
}))

const ITEM = {
  id: 'i-1',
  position: 0,
  test_type_key: 'tensile',
  test_type_label: '인장시험',
  conditions: { temperature: 298.15 },
  input_units: { temperature: 'degC' },
  orientations: ['MD'],
  count: 1,
  runs: [],
}

vi.mock('@/modules/commissions/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/commissions/api')>()),
  commissionsApi: {
    get: () => Promise.resolve({ id: 'c-1', seq: 7, items: [ITEM] }),
    linkRun: (...args: unknown[]) => linkRun(...args),
  },
}))

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    samples: () => Promise.resolve([]),
    specimens: () => Promise.resolve([]),
    createSpecimen: (...args: unknown[]) => createSpecimen(...args),
  },
}))

vi.mock('@/modules/materials/MaterialPicker', () => ({ MaterialPicker: () => null }))
vi.mock('@/modules/vocabulary/VocabularyField', () => ({ VocabularyField: () => null }))

beforeEach(() => {
  vi.clearAllMocks()
  createSpecimen.mockResolvedValue({ id: 'sp-1', orientation: 'MD' })
  upload.mockResolvedValue({ id: 'run-9' })
  linkRun.mockResolvedValue({})
})

async function uploadOne() {
  const user = userEvent.setup()
  const { container } = render(
    <MemoryRouter initialEntries={['/tests/upload?material=m-1&sample=s-1&commission=c-1&item=i-1']}>
      <BatchUploadPage />
    </MemoryRouter>
  )
  // 의뢰를 다 받은 뒤에 담는다 — 그 전에 담으면 종류가 항목에서 안 온다.
  expect(await screen.findByText(/측정 의뢰 #7 · 1번 항목/)).toBeInTheDocument()
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, new File(['x'], 'a.tra'))
  await user.click(await screen.findByRole('button', { name: 'MD' }))
  await user.click(screen.getByRole('button', { name: '업로드 (1)' }))
}

describe('측정 의뢰의 항목에서 올린다', () => {
  it('종류 · 조건을 항목에서 채우고, 올린 시험을 그 항목에 붙인다', async () => {
    await uploadOne()
    await waitFor(() => expect(linkRun).toHaveBeenCalledWith('c-1', 'i-1', 'run-9'))
    expect(upload).toHaveBeenCalledWith(
      expect.objectContaining({
        specimenId: 'sp-1',
        testType: 'tensile',
        conditions: { temperature: 25 },
      })
    )
    expect(await screen.findByText('올림')).toBeInTheDocument()
  })

  it('붙이기가 막혀도 올린 것은 남고, 그 줄에 이유를 적는다', async () => {
    linkRun.mockRejectedValue(new Error('이 의뢰를 고칠 권한이 없습니다'))
    await uploadOne()
    expect(
      await screen.findByText('올렸지만 의뢰에 못 붙였습니다 — 이 의뢰를 고칠 권한이 없습니다')
    ).toBeInTheDocument()
    expect(screen.getByText('올림')).toBeInTheDocument()
  })
})
