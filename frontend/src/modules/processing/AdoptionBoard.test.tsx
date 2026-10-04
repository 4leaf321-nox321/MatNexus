/**
 * 채택 검토대 — **견주고, 누르기 전에 세어 보이고, 되돌린다**(ADR 0058).
 *
 *   튀는 것이 위에 · 칠해진다       한 건씩 보면 그럴듯한 것이 견주면 보인다
 *   지금 채택은 기본으로 안 옮긴다   말없이 바꾸지 않는다
 *   못 고치는 시험은 못 고른다       누르기 전에 화면이 안다
 *   누르기 전에 무엇이 바뀌나 센다   새로 · 바꿈 · 문턱 넘은 것
 *   되돌리면 이전 채택으로          채택은 결과를 안 지우므로 돌려놓을 수 있다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdoptionBoard } from '@/modules/processing/AdoptionBoard'

const overview = vi.fn()
const lines = vi.fn()
const adoptMany = vi.fn()

vi.mock('@/modules/processing/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/processing/api')>()),
  processingApi: {
    overview: (...args: unknown[]) => overview(...args),
    lines: (...args: unknown[]) => lines(...args),
    adoptMany: (...args: unknown[]) => adoptMany(...args),
  },
}))
// 한 건 자세히의 그림은 결과 탭의 것이다 — 그 시험이 본다.
vi.mock('@/modules/processing/ResultsPanel', () => ({
  ResultCurve: ({ resultId }: { resultId: string }) => <div>결과 그림 {resultId}</div>,
}))
vi.mock('@/modules/tests/CurveChart', () => ({
  CurveChart: (props: { pointsLabel?: string; background?: { label: string; tone?: string }[] }) => (
    <div aria-label="겹친 그림">
      굵은 선 {props.pointsLabel} · 뒤에 깐 선{' '}
      {(props.background ?? []).map((one) => `${one.label}${one.tone ? '(칠함)' : ''}`).join(',')}
    </div>
  ),
}))

function result(id: string, modulus: number, over: Record<string, unknown> = {}) {
  return {
    id,
    created_at: '2026-10-01T09:00:00Z',
    recipe_key: null,
    recipe_label: '인장 기본',
    step_count: 3,
    row_count: 100,
    has_true_stress: false,
    stale: false,
    is_adopted: false,
    scalars: [
      { key: 'youngs_modulus', label: '탄성계수', value: modulus * 1e9, si_unit: 'Pa', dimension: null },
    ],
    ...over,
  }
}

function runOf(id: string, results: ReturnType<typeof result>[], over: Record<string, unknown> = {}) {
  return {
    test_run_id: id,
    found: true,
    code: `T-${id}`,
    record_name: `시편-${id}`,
    status: 'parsed',
    test_type_key: 'tensile',
    test_type_label: '인장',
    material_id: 'm1',
    material_name: 'SECC',
    specimen_name: null,
    orientation: 'MD',
    adopted_result_id: null,
    access: { can_edit: true, can_hand_over: false, registrant: null, edit_workspace: null, reason: null },
    results,
    ...over,
  }
}

const RUNS = [
  runOf('1', [result('r1', 150)]),
  runOf('2', [result('r2', 210)]),
  // 지금 채택(r3a)이 있다 — 더 최근 결과(r3b)가 있어도 **기본은 지금 채택**이다.
  runOf('3', [result('r3b', 100), result('r3a', 205, { is_adopted: true })], {
    adopted_result_id: 'r3a',
  }),
  runOf('4', [result('r4', 198)], {
    access: {
      can_edit: false,
      can_hand_over: false,
      registrant: '홍길동',
      edit_workspace: null,
      reason: '등록자 홍길동에게 물으세요',
    },
  }),
  { ...runOf('5', []), found: false, record_name: '?' },
]

function show() {
  render(
    <MemoryRouter>
      <AdoptionBoard testRunIds={['1', '2', '3', '4', '5']} />
    </MemoryRouter>
  )
}

/** 데이터로 그려진 줄 — API 가 불렸는지가 아니라 그려진 것을 기다린다(AGENTS.md). */
async function rowOf(name: string) {
  // 보고 있는 시험은 자세히 보기의 제목에도 이름이 선다 — 표의 줄을 고른다.
  const cells = await screen.findAllByText(name)
  const cell = cells.find((one) => one.closest('tr'))!
  return within(cell.closest('tr')!)
}

beforeEach(() => {
  vi.clearAllMocks()
  overview.mockResolvedValue(RUNS)
  lines.mockImplementation((ids: string[]) =>
    Promise.resolve(
      ids.map((id) => ({
        result_id: id,
        test_run_id: id,
        x: 'strain_engineering',
        y: 'stress_engineering',
        units: { strain_engineering: '1', stress_engineering: 'Pa' },
        points: [
          [0, 0],
          [0.1, 1e8],
        ],
      }))
    )
  )
  adoptMany.mockResolvedValue({ requested: 0, changed: 0, unchanged: 0, failed: 0, items: [] })
})

describe('견준다', () => {
  it('중앙값에서 먼 것이 위에 서고 칠해진다', async () => {
    show()
    const outlier = await rowOf('시편-1')
    // 중앙값 201.5 GPa — 150 은 25.6% 낮다.
    expect(outlier.getByText(/-25\.6%/)).toBeInTheDocument()
    expect(screen.getByText('중앙값에서 먼 것 1')).toBeInTheDocument()
    const order = screen.getAllByRole('row').slice(1).map((one) => one.textContent ?? '')
    expect(order[0]).toContain('시편-1')
    // 볼 수 없는 시험은 맨 아래 — 줄은 지킨다.
    expect(order.at(-1)).toContain('볼 수 없는 시험입니다')
  })

  it('보고 있는 시험을 굵게, 튀는 시험을 칠해 겹친다', async () => {
    show()
    expect(await screen.findByLabelText('겹친 그림')).toHaveTextContent('굵은 선 시편-1')
    // 보고 있는 것이 먼저 읽힌다 — 상한에 걸려도 그것은 그린다.
    expect(lines.mock.calls[0][0][0]).toBe('r1')
    await screen.findByText('결과 그림 r1')
  })

  it('줄을 누르면 그 시험을 자세히 본다 — 결과 탭의 그 그림', async () => {
    show()
    const row = await rowOf('시편-2')
    await userEvent.click(row.getByText('SECC'))
    expect(await screen.findByText('결과 그림 r2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /이 시험 열기/ })).toHaveAttribute(
      'href',
      '/test-runs/2?tab=results'
    )
  })
})

describe('기본으로 고르는 것', () => {
  it('채택 전인 것만 고르고, 지금 채택과 못 고치는 시험은 안 고른다', async () => {
    show()
    expect(await screen.findByRole('button', { name: '고른 2건 채택' })).toBeEnabled()
    expect((await rowOf('시편-1')).getByRole('checkbox')).toBeChecked()
    expect((await rowOf('시편-3')).getByRole('checkbox')).not.toBeChecked()
    expect((await rowOf('시편-3')).getByText('채택됨')).toBeInTheDocument()
    const locked = await rowOf('시편-4')
    expect(locked.getByRole('checkbox')).toBeDisabled()
    expect(locked.getByText('고칠 수 없음')).toBeInTheDocument()
  })

  it('다른 결과를 고르면 「바꿈」 이 되고 고른 것에 든다', async () => {
    show()
    const row = await rowOf('시편-3')
    await userEvent.selectOptions(row.getByLabelText('시편-3 결과'), 'r3b')
    expect(row.getByText('바꿈')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '고른 3건 채택' })).toBeEnabled()
    // 지금 채택 → 고른 결과의 값 차이가 자세히 보기에 선다.
    expect(within(screen.getByLabelText('지금 채택과 차이')).getByText('탄성계수')).toBeInTheDocument()
  })
})

describe('누르기 전에 세고, 누른 뒤 되돌린다', () => {
  it('새로 · 바꿈 · 문턱 넘은 것을 세어 묻는다', async () => {
    show()
    const row = await rowOf('시편-3')
    await userEvent.selectOptions(row.getByLabelText('시편-3 결과'), 'r3b')
    await userEvent.click(screen.getByRole('button', { name: '고른 3건 채택' }))
    const dialog = within(await screen.findByRole('dialog'))
    expect(dialog.getByText(/새로 채택/)).toHaveTextContent('새로 채택 2건 · 다른 결과로 바꿈 1건')
    // r3b(100 GPa)를 고르면 중앙값이 174 로 내려가 셋 다 10% 밖이다.
    expect(dialog.getByText(/문턱\(10%\)보다 먼 것이 3건/)).toBeInTheDocument()
    // 못 고치는 시험은 못 고르지만, **몇 건이 빠지는지는 말한다.**
    expect(dialog.getByText(/고칠 수 없는 시험 1건은 이번 채택에서 빠집니다/)).toBeInTheDocument()
    expect(adoptMany).not.toHaveBeenCalled()
  })

  it('채택하고, 되돌리면 이전 채택으로 돌려놓는다', async () => {
    adoptMany.mockResolvedValueOnce({
      requested: 3,
      changed: 3,
      unchanged: 0,
      failed: 0,
      items: [
        { test_run_id: '1', record_name: '시편-1', status: 'ok', previous_adopted_id: null, adopted_result_id: 'r1' },
        { test_run_id: '2', record_name: '시편-2', status: 'ok', previous_adopted_id: null, adopted_result_id: 'r2' },
        { test_run_id: '3', record_name: '시편-3', status: 'ok', previous_adopted_id: 'r3a', adopted_result_id: 'r3b' },
      ],
    })
    show()
    const row = await rowOf('시편-3')
    await userEvent.selectOptions(row.getByLabelText('시편-3 결과'), 'r3b')
    await userEvent.click(screen.getByRole('button', { name: '고른 3건 채택' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '채택' }))

    await waitFor(() => expect(adoptMany).toHaveBeenCalledTimes(1))
    expect(adoptMany.mock.calls[0][0]).toEqual([
      { test_run_id: '1', result_id: 'r1' },
      { test_run_id: '2', result_id: 'r2' },
      { test_run_id: '3', result_id: 'r3b' },
    ])
    const outcome = within(await screen.findByLabelText('채택 결과'))
    expect(outcome.getByText('3건을 채택했습니다.')).toBeInTheDocument()

    await userEvent.click(outcome.getByRole('button', { name: /되돌리기/ }))
    await waitFor(() => expect(adoptMany).toHaveBeenCalledTimes(2))
    // **채택 전이던 것은 거두고, 다른 것을 채택하던 것은 그것으로.**
    expect(adoptMany.mock.calls[1][0]).toEqual([
      { test_run_id: '1', result_id: null },
      { test_run_id: '2', result_id: null },
      { test_run_id: '3', result_id: 'r3a' },
    ])
    expect(await screen.findByText(/되돌렸습니다/)).toBeInTheDocument()
  })

  it('막힌 건은 까닭과 함께 그 줄을 말한다', async () => {
    adoptMany.mockResolvedValueOnce({
      requested: 2,
      changed: 1,
      unchanged: 0,
      failed: 1,
      items: [
        { test_run_id: '1', record_name: '시편-1', status: 'ok', previous_adopted_id: null, adopted_result_id: 'r1' },
        { test_run_id: '2', record_name: '시편-2', status: 'failed', previous_adopted_id: null, adopted_result_id: null, error: '이름이 긴 값' },
      ],
    })
    show()
    await userEvent.click(await screen.findByRole('button', { name: '고른 2건 채택' }))
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '채택' }))
    const outcome = within(await screen.findByLabelText('채택 결과'))
    expect(outcome.getByText(/이름이 긴 값/)).toBeInTheDocument()
    expect(outcome.getByText('실패 1')).toBeInTheDocument()
  })
})
