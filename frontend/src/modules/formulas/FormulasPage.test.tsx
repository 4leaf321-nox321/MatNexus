/**
 * 계산식 화면 — **쓰는 곳이 있는 식은 지우기가 막히고, 값 단계는 입력·결과를 채워 보낸다.**
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import FormulasPage from '@/modules/formulas/FormulasPage'
import type { Formula } from '@/modules/formulas/api'

const list = vi.fn()
const vocabulary = vi.fn()
const create = vi.fn()
const update = vi.fn()

vi.mock('@/modules/formulas/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/formulas/api')>()),
  formulasApi: {
    list: (...args: unknown[]) => list(...args),
    vocabulary: (...args: unknown[]) => vocabulary(...args),
    create: (...args: unknown[]) => create(...args),
    update: (...args: unknown[]) => update(...args),
    remove: vi.fn(),
    preview: vi.fn(),
  },
}))
vi.mock('@/modules/tests/api', () => ({ testsApi: { runs: vi.fn().mockResolvedValue({ items: [] }) } }))

const USED: Formula = {
  id: 'f-1',
  key: 'yield_ratio',
  registry_key: 'formula.yield_ratio',
  kind: 'scalar_step',
  kind_label: '값 단계',
  label: '항복비',
  expression: 'proof_stress / tensile_strength',
  describe: null,
  variables: [
    { name: 'proof_stress', unit: 'Pa' },
    { name: 'tensile_strength', unit: 'Pa' },
  ],
  parameters: [],
  result: { key: 'yield_ratio', label: '항복비', si_unit: '1' },
  x_column: null,
  y_column: null,
  block: null,
  applies_to: ['tensile'],
  version: 2,
  enabled: true,
  created_by: '관리자',
  created_at: '2026-09-13T00:00:00Z',
  updated_at: '2026-09-13T00:00:00Z',
  references: { recipes: 1, results: 3, cards: 0 },
}
const FREE: Formula = {
  ...USED,
  id: 'f-2',
  key: 'swift2',
  registry_key: 'formula.swift2',
  kind: 'family',
  kind_label: '적합식',
  label: 'Swift 2',
  expression: 'K * pow(e0 + x, n)',
  references: { recipes: 0, results: 0, cards: 0 },
}

beforeEach(() => {
  vi.clearAllMocks()
  list.mockResolvedValue([USED, FREE])
  vocabulary.mockResolvedValue({
    columns: [{ key: 'stress_true', label: '진응력 (Pa)' }],
    scalars: [{ key: 'proof_stress', label: '항복강도 (Pa)' }],
    blocks: [{ key: 'hardening', label: '경화' }],
    functions: ['pow', 'exp'],
    constants: ['pi'],
  })
  create.mockResolvedValue({ ...USED, id: 'f-3', label: '새 식', version: 1 })
})

describe('FormulasPage', () => {
  it('쓰는 곳이 있는 식은 지우기가 막히고, 판과 쓰는 곳이 표에 보인다', async () => {
    render(<FormulasPage />)
    const used = (await screen.findByText('항복비')).closest('tr') as HTMLElement
    expect(within(used).getByText('v2')).toBeInTheDocument()
    expect(within(used).getByText('레시피 1 · 결과 3')).toBeInTheDocument()
    expect(within(used).getByTitle(/못 지웁니다/)).toBeDisabled()

    const free = screen.getByText('Swift 2').closest('tr') as HTMLElement
    expect(within(free).getByText('없음')).toBeInTheDocument()
    expect(within(free).getByTitle('삭제')).toBeEnabled()
  })

  it('값 단계를 적어 보내면 입력·결과·시험 종류가 서버 모양으로 간다', async () => {
    const user = userEvent.setup()
    render(<FormulasPage />)
    await screen.findByText('항복비')
    await user.click(screen.getByRole('button', { name: '값 단계' }))

    await user.type(screen.getByLabelText('키'), 'ratio2')
    await user.type(screen.getByLabelText('이름'), '비율')
    await user.type(screen.getByLabelText('식'), 'a * 2')
    const names = screen.getAllByPlaceholderText('이름')
    await user.type(names[0], 'a')
    expect(screen.getByRole('button', { name: '생성' })).toBeDisabled()
    await user.type(screen.getByLabelText('내는 값의 키'), 'ratio2')
    await user.type(screen.getByLabelText('내는 값의 이름'), '비율')
    await user.type(screen.getByLabelText(/시험 종류/), 'tensile, compression')
    await user.click(screen.getByRole('button', { name: '생성' }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    const [payload] = create.mock.calls[0] as [Record<string, unknown>]
    expect(payload).toMatchObject({
      key: 'ratio2',
      kind: 'scalar_step',
      expression: 'a * 2',
      variables: [{ name: 'a', unit: '1' }],
      result: { key: 'ratio2', label: '비율', si_unit: '1' },
      applies_to: ['tensile', 'compression'],
    })
  })
})
