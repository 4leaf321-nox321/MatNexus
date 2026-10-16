/**
 * 시편 규격의 처리 기본값 고치기(2026-10-16).
 *
 *   이름으로 보인다     `flexural.modulus · method` 가 아니라 「굽힘 탄성률 · 방법 = 접선」
 *   선택지는 고른다     없는 선택지를 적으면 처리 화면이 조용히 버린다
 *   빈 칸은 비움       굽힘의 하중 스팬을 비우면 3점이다
 *   목록은 필요할 때만  규격 창을 열 때마다 처리 단계 전부를 부르지 않는다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StandardDefaultsEditor } from '@/modules/processing/StandardDefaultsEditor'

const steps = vi.fn()

vi.mock('@/modules/processing/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/processing/api')>()),
  processingApi: { steps: () => steps() },
}))

const param = (over: Record<string, unknown>) => ({
  type: 'float',
  default: null,
  choices: [],
  choice_labels: {},
  unit: null,
  dimension: null,
  help: null,
  required: false,
  role: null,
  when: {},
  ...over,
})

const CATALOG = [
  {
    id: 'flexural.engineering',
    label: '굽힘 응력-변형률',
    params: [param({ name: 'load_span', label: '하중 스팬 Lᵢ (4점)', unit: 'm', dimension: 'length' })],
  },
  {
    id: 'flexural.modulus',
    label: '굽힘 탄성률 (등가 E)',
    params: [
      param({
        name: 'method',
        label: '방법',
        type: 'choice',
        default: 'chord',
        choices: ['chord', 'tangent'],
        choice_labels: { chord: '현', tangent: '접선' },
      }),
      param({ name: 'maximum_strain', label: '구간 끝', unit: '1', dimension: 'strain', default: 0.0025 }),
    ],
  },
]

describe('처리 기본값 고치기', () => {
  beforeEach(() => {
    steps.mockReset()
    steps.mockResolvedValue(CATALOG)
  })

  it('비어 있으면 처리 단계 목록을 부르지 않는다', () => {
    render(<StandardDefaultsEditor value={{}} onChange={vi.fn()} />)
    expect(steps).not.toHaveBeenCalled()
    expect(screen.getByText(/시험 종류의 기본 순서 그대로/)).toBeInTheDocument()
  })

  it('이름으로 보이고, 선택지를 바꾸면 그 값으로 낸다', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <StandardDefaultsEditor
        value={{ 'flexural.modulus': { method: 'tangent' } }}
        onChange={onChange}
      />
    )
    const method = await screen.findByLabelText('굽힘 탄성률 (등가 E) · 방법')
    await waitFor(() => expect(method).toHaveValue('tangent'))
    await user.selectOptions(method, 'chord')
    expect(onChange).toHaveBeenLastCalledWith({ 'flexural.modulus': { method: 'chord' } })
  })

  it('빈 칸은 비움(null)으로 낸다 — 하중 스팬을 비우면 3점', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <StandardDefaultsEditor
        value={{ 'flexural.engineering': { load_span: '@specimen_load_span' } }}
        onChange={onChange}
      />
    )
    const span = await screen.findByRole('textbox', { name: /굽힘 응력-변형률 · 하중 스팬/ })
    expect(span).toHaveValue('@specimen_load_span')
    await user.clear(span)
    expect(onChange).toHaveBeenLastCalledWith({ 'flexural.engineering': { load_span: null } })
  })

  it('길이는 실무 단위로 보이고 SI 로 낸다', async () => {
    // **목록이 오기 전에 칸을 그리면** SI 숫자(0.02)가 글자로 남아 (mm) 라벨 옆에 선다.
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <StandardDefaultsEditor
        value={{ 'flexural.engineering': { load_span: 0.02 } }}
        onChange={onChange}
      />
    )
    const span = await screen.findByRole('textbox', { name: /하중 스팬 Lᵢ \(4점\) \(mm\)/ })
    expect(span).toHaveValue('20')
    await user.clear(span)
    await user.type(span, '25')
    expect(onChange).toHaveBeenLastCalledWith({ 'flexural.engineering': { load_span: 0.025 } })
  })

  it('빼면 그 단계 묶음이 비어 사라진다', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <StandardDefaultsEditor
        value={{ 'flexural.modulus': { method: 'tangent' } }}
        onChange={onChange}
      />
    )
    await user.click(await screen.findByRole('button', { name: /방법 빼기/ }))
    expect(onChange).toHaveBeenLastCalledWith({})
  })

  it('단계와 옵션을 골라 더하면 그 옵션의 기본값에서 시작한다', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<StandardDefaultsEditor value={{}} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /옵션 추가/ }))
    const step = await screen.findByLabelText('더할 처리 단계')
    await waitFor(() => expect(step).toHaveTextContent('굽힘 탄성률 (등가 E)'))
    await user.selectOptions(step, 'flexural.modulus')
    await user.selectOptions(screen.getByLabelText('더할 옵션'), 'maximum_strain')
    await user.click(screen.getByRole('button', { name: '더하기' }))
    expect(onChange).toHaveBeenLastCalledWith({ 'flexural.modulus': { maximum_strain: 0.0025 } })
  })
})
