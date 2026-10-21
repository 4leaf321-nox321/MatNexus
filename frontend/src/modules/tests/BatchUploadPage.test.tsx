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
const formats = vi.fn()
const detectType = vi.fn()
const types = vi.fn()

const TENSILE = {
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
}

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: (...args: unknown[]) => types(...args),
    detectType: (...args: unknown[]) => detectType(...args),
    formats: (...args: unknown[]) => formats(...args),
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
  types.mockResolvedValue([TENSILE])
  createSpecimen.mockResolvedValue({ id: 'sp-1', orientation: 'MD' })
  upload.mockResolvedValue({ id: 'run-9' })
  linkRun.mockResolvedValue({})
  formats.mockResolvedValue([])
  detectType.mockResolvedValue({ test_type_key: null, reason: '모르는 형식' })
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
const profile = (key: string, label: string) => ({
  key,
  label,
  test_type_key: 'tensile',
  test_type_label: '인장시험',
  is_active: true,
  priority: 0,
})

describe('읽을 형식 (2026-10-20)', () => {
  it('맞는 형식이 둘이면 그 줄에 말하고, 고른 형식으로 올린다', async () => {
    formats.mockResolvedValue([profile('zwick_a', 'Zwick 기본'), profile('zwick_b', 'Zwick 다단')])
    detectType.mockResolvedValue({
      filename: 'a.tra',
      test_type_key: 'tensile',
      test_type_label: '인장시험',
      profile_key: 'zwick_a',
      profile_candidates: ['zwick_a', 'zwick_b'],
      source: 'profile',
      reason: '맞는 형식이 2개입니다',
    })
    const user = userEvent.setup()
    const { container } = render(
      <MemoryRouter initialEntries={['/tests/upload?material=m-1&sample=s-1&commission=c-1&item=i-1']}>
        <BatchUploadPage />
      </MemoryRouter>
    )
    expect(await screen.findByText(/측정 의뢰 #7 · 1번 항목/)).toBeInTheDocument()
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['x'], 'a.tra'))

    // 자동은 첫 번째로 읽는다 — 틀릴 수 있다는 것을 그 줄에서 말한다.
    expect(await screen.findByText('맞는 형식 2개 — 확인')).toBeInTheDocument()
    await user.click(screen.getByRole('combobox', { name: '읽을 형식' }))
    await user.click(screen.getByRole('option', { name: /Zwick 다단/ }))
    expect(screen.queryByText('맞는 형식 2개 — 확인')).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'MD' }))
    await user.click(screen.getByRole('button', { name: '업로드 (1)' }))
    await waitFor(() =>
      expect(upload).toHaveBeenCalledWith(expect.objectContaining({ profileKey: 'zwick_b' }))
    )
  })

  it('고른 줄의 종류를 일괄로 바꾸면 고른 형식을 비운다', async () => {
    // 새 종류에 형식이 하나뿐이면 칸이 안 보인다 — 옛 형식이 남으면 실려 가 서버가 422 로 막았다.
    types.mockResolvedValue([TENSILE, { ...TENSILE, key: 'flexural', label: '굽힘시험' }])
    formats.mockResolvedValue([profile('zwick_a', 'Zwick 기본'), profile('zwick_b', 'Zwick 다단')])
    const user = userEvent.setup()
    const { container } = render(
      <MemoryRouter initialEntries={['/tests/upload?material=m-1&sample=s-1&commission=c-1&item=i-1']}>
        <BatchUploadPage />
      </MemoryRouter>
    )
    expect(await screen.findByText(/측정 의뢰 #7 · 1번 항목/)).toBeInTheDocument()
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['x'], 'a.tra'))
    await user.click(await screen.findByRole('combobox', { name: '읽을 형식' }))
    await user.click(screen.getByRole('option', { name: /Zwick 다단/ }))

    await user.click(screen.getByRole('combobox', { name: '시험 종류 일괄 지정' }))
    await user.click(await screen.findByRole('option', { name: '굽힘시험' }))
    expect(screen.queryByRole('combobox', { name: '읽을 형식' })).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'MD' }))
    await user.click(screen.getByRole('button', { name: '업로드 (1)' }))
    await waitFor(() =>
      expect(upload).toHaveBeenCalledWith(expect.objectContaining({ testType: 'flexural' }))
    )
    expect(upload.mock.calls[0]?.[0]?.profileKey).toBeUndefined()
  })
})
