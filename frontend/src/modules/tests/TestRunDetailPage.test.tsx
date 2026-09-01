/**
 * 시험 상세 — **전체 화면으로 넓혀 보고, 손쉽게 되돌아온다.**
 *
 * 이 화면은 곡선과 표를 나란히 놓고 「장비가 160 이라는데 곡선이 그렇게 보이나」 를
 * 묻는 자리라, 폭이 곧 읽히는 양이다. 그래서 사이드바·머리말이 덮는 자리를 잠시
 * 걷을 수 있어야 한다.
 *
 * 화면을 덮는 것에는 **늘 손쉬운 출구**가 있어야 한다 — 못 걷으면 갇힌 것처럼 느낀다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TestRunDetailPage from '@/modules/tests/TestRunDetailPage'

const run = vi.fn()
const types = vi.fn()
const formats = vi.fn()
const curve = vi.fn()
const dimensions = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    run: (...args: unknown[]) => run(...args),
    types: () => types(),
    formats: (...args: unknown[]) => formats(...args),
    curve: (...args: unknown[]) => curve(...args),
    instrumentDimensions: (...args: unknown[]) => dimensions(...args),
  },
}))

// 곁의 무거운 판들은 자기 시험이 따로 본다 — 여기서는 껍데기만 있으면 된다.
vi.mock('@/modules/processing/ProcessingPanel', () => ({ ProcessingPanel: () => <div /> }))
vi.mock('@/modules/processing/ResultsPanel', () => ({ ResultsPanel: () => <div /> }))
vi.mock('@/modules/viscoelastic/ViscoelasticPanel', () => ({ ViscoelasticPanel: () => <div /> }))
vi.mock('@/modules/viscoelastic/ViscoelasticSummary', () => ({
  ViscoelasticSummary: () => <div />,
}))
vi.mock('@/modules/tests/CurveChart', () => ({ CurveChart: () => <div /> }))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
  useMaybeAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useParams: () => ({ id: 'r1' }),
}))

const DETAIL = {
  id: 'r1',
  record_name: 'SECC-01 인장',
  status: 'parsed',
  test_type_key: 'tensile',
  test_type_label: '인장시험',
  result_count: 0,
  curves: [],
  summary: [],
  summaries: [],
  conditions: {},
  source_metadata: {},
  condition_fields: [],
  specimen_id: 's1',
  source_filename: 'a.csv',
  material_id: 'm1',
  warnings: [],
}

function show() {
  render(
    <MemoryRouter>
      <TestRunDetailPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  run.mockResolvedValue(DETAIL)
  types.mockResolvedValue([])
  formats.mockResolvedValue([])
  curve.mockResolvedValue({ columns: {}, rows: 0 })
  dimensions.mockResolvedValue({ items: [] })
})

describe('전체 화면', () => {
  it('탭 줄에서 켜고 끈다', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: '전체 화면' }))
    expect(await screen.findByRole('button', { name: '전체 화면 나가기' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '전체 화면 나가기' }))
    expect(await screen.findByRole('button', { name: '전체 화면' })).toBeInTheDocument()
  })

  it('Esc 로 나온다', async () => {
    // **덮은 것을 못 걷으면 갇힌 것처럼 느낀다.** 단추를 못 찾아도 나올 길이 있다.
    show()
    await userEvent.click(await screen.findByRole('button', { name: '전체 화면' }))
    await userEvent.keyboard('{Escape}')
    expect(await screen.findByRole('button', { name: '전체 화면' })).toBeInTheDocument()
  })
})
