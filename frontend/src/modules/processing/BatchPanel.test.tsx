/**
 * 한 번에 처리 — **시험 종류마다 따로, 곡선이 있는 것만**(ADR 0058).
 *
 * 레시피는 시험 종류의 것이다. 섞인 바구니에 인장 레시피를 통째로 걸면 DMA 건마다 실패하고,
 * 그 실패 스무 줄은 무엇을 고쳐야 하는지 말하지 않는다.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BatchByType, BatchPanel, BatchResultRow } from '@/modules/processing/BatchPanel'
import { curveOptions, plannedCount } from '@/modules/processing/batchRun'

const overview = vi.fn()
const recipes = vi.fn()
const batch = vi.fn()

vi.mock('@/modules/processing/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/processing/api')>()),
  processingApi: {
    overview: (...args: unknown[]) => overview(...args),
    recipes: (...args: unknown[]) => recipes(...args),
    batch: (...args: unknown[]) => batch(...args),
  },
}))

function runOf(id: string, type: string, label: string, over: Record<string, unknown> = {}) {
  return {
    test_run_id: id,
    found: true,
    record_name: id,
    status: 'parsed',
    test_type_key: type,
    test_type_label: label,
    adopted_result_id: null,
    results: [],
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  recipes.mockResolvedValue([])
  overview.mockResolvedValue([
    runOf('t1', 'tensile', '인장'),
    runOf('t2', 'tensile', '인장'),
    runOf('d1', 'dma_sweep', 'DMA'),
    runOf('x1', 'tensile', '인장', { status: 'imported' }),
    runOf('x2', 'tensile', '인장', { status: 'failed' }),
  ])
})

describe('한 번에 처리', () => {
  it('종류마다 판을 세우고, 그 종류의 레시피만 묻는다', async () => {
    render(<BatchByType testRunIds={['t1', 't2', 'd1', 'x1', 'x2']} onDone={vi.fn()} />)
    const kinds = within(await screen.findByLabelText('시험 종류'))
    expect(kinds.getByRole('button', { name: '인장 2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('인장 2건에 같은 단계 적용')).toBeInTheDocument()
    expect(recipes).toHaveBeenCalledWith('tensile')

    await userEvent.click(kinds.getByRole('button', { name: 'DMA 1' }))
    expect(await screen.findByText('DMA 1건에 같은 단계 적용')).toBeInTheDocument()
    expect(recipes).toHaveBeenLastCalledWith('dma_sweep')
  })

  it('곡선이 없는 시험은 세어서 말하고 뺀다', async () => {
    // 표로 입력 · 읽기 실패는 처리할 곡선이 없다.
    render(<BatchByType testRunIds={['t1', 't2', 'd1', 'x1', 'x2']} onDone={vi.fn()} />)
    expect(await screen.findByText(/2건은 읽힌 곡선이 없어/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /2건 미리보기/ })).toBeInTheDocument()
  })

  it('바로 채택은 꺼 둔다 — 다음 단계가 채택 검토대다', async () => {
    // 저장하고 바로 채택하면 견주어 볼 자리를 건너뛴다(ADR 0058). 창에서는 전처럼 켜 둔다.
    render(<BatchByType testRunIds={['t1', 't2']} onDone={vi.fn()} />)
    expect(await screen.findByRole('checkbox', { name: /바로 채택/ })).not.toBeChecked()
  })

  it('담은 시험이 없으면 앞 단계로 보낸다', () => {
    render(<BatchByType testRunIds={[]} onDone={vi.fn()} />)
    expect(screen.getByText(/앞 단계에서 시험을 담으면/)).toBeInTheDocument()
    expect(overview).not.toHaveBeenCalled()
  })
})

describe('일괄 결과 한 줄', () => {
  it('부분 결과면 무엇이 빠졌고 채택을 왜 안 옮겼는지 그 줄에서 말한다', () => {
    // v1.285.0 보고: 한 단계가 걸리면 인장강도까지 저장되지 않았다 — 이제 저장은 되고, 빠진 것이 보인다.
    render(
      <BatchResultRow
        item={{
          test_run_id: 't1',
          record_name: 'SPCC_T01',
          status: 'ok',
          adopted: false,
          result_id: 'r1',
          scalars: [{ key: 'tensile_strength', label: '인장강도', value: 3e8, si_unit: 'Pa' }],
          previous: [],
          failures: [
            {
              index: 2,
              plugin: 'tensile.proof_stress',
              label: '오프셋 항복강도',
              message: "3단계: '@youngs_modulus' 가 가리키는 값을 앞 단계가 내지 않았습니다.",
              stopped: false,
            },
          ],
          warning: '부분 결과라 채택은 그대로 두었습니다 — 지금 채택된 값 중 항복강도 이(가) 이 결과에 없습니다.',
        }}
      />
    )
    expect(screen.getByText('부분 결과 · 실패 1단계')).toBeInTheDocument()
    expect(screen.getByText(/건너뜀 — 3단계: '@youngs_modulus'/)).toBeInTheDocument()
    expect(screen.getByText(/채택은 그대로 두었습니다/)).toBeInTheDocument()
  })
})

describe('다온도 시험의 곡선 고르기', () => {
  // v1.285.0 보고: 곡선을 고르지 않으면 키 글자순 첫 곡선 하나만 처리됐다.
  const curve = (key: string, kind = 'measured') => ({ key, label: `${key} °C`, kind, row_count: 8 })
  const RUNS = [
    runOf('a', 'dma_sweep', 'DMA', { curves: [curve('20'), curve('40'), curve('tts', 'derived')] }),
    runOf('b', 'dma_sweep', 'DMA', { curves: [curve('20'), curve('60')] }),
  ]

  it('측정 곡선만 키마다 센다 — 장비가 계산한 곡선은 뺀다', () => {
    const { several, options } = curveOptions(RUNS as never)
    expect(several).toBe(true)
    expect(options.map((one) => [one.key, one.count])).toEqual([
      ['20', 2],
      ['40', 1],
      ['60', 1],
    ])
    expect(plannedCount(RUNS as never, 'first')).toBe(2)
    expect(plannedCount(RUNS as never, 'all')).toBe(4)
    expect(plannedCount(RUNS as never, ['20'])).toBe(2)
  })

  it('측정 곡선 전부를 고르면 그대로 서버에 싣는다', async () => {
    batch.mockResolvedValue({ requested: 4, succeeded: 4, failed: 0, dry_run: true, items: [] })
    const user = userEvent.setup()
    render(
      <BatchPanel
        testRunIds={['a', 'b']}
        testTypeKey="dma_sweep"
        steps={[{ plugin: 'dma.derived', options: {} }]}
        runs={RUNS as never}
        onDone={vi.fn()}
      />
    )
    await user.click(screen.getByRole('radio', { name: /측정 곡선 전부 \(4개\)/ }))
    expect(screen.getByText(/한 시험에서 곡선을 둘 이상 돌리면/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '시험 2건 · 곡선 4개 미리보기' }))
    expect(batch).toHaveBeenCalledWith(expect.objectContaining({ curves: 'all', dry_run: true }))
  })

  it('곡선을 고르면 고른 키만 싣고, 안 고르면 못 누른다', async () => {
    batch.mockResolvedValue({ requested: 2, succeeded: 2, failed: 0, dry_run: true, items: [] })
    const user = userEvent.setup()
    render(
      <BatchPanel
        testRunIds={['a', 'b']}
        testTypeKey="dma_sweep"
        steps={[{ plugin: 'dma.derived', options: {} }]}
        runs={RUNS as never}
        onDone={vi.fn()}
      />
    )
    await user.click(screen.getByRole('radio', { name: '곡선 고르기' }))
    expect(screen.getByRole('button', { name: /곡선 0개 미리보기/ })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: '20 °C 곡선' }))
    await user.click(screen.getByRole('button', { name: '시험 2건 · 곡선 2개 미리보기' }))
    expect(batch).toHaveBeenCalledWith(expect.objectContaining({ curves: ['20'] }))
  })

  it('곡선이 하나뿐인 시험들에는 고를 칸을 안 세운다', () => {
    render(
      <BatchPanel
        testRunIds={['t1']}
        testTypeKey="tensile"
        steps={[{ plugin: 'tensile.strength', options: {} }]}
        runs={[runOf('t1', 'tensile', '인장', { curves: [curve('raw')] })] as never}
        onDone={vi.fn()}
      />
    )
    expect(screen.queryByText('돌릴 곡선')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1건 미리보기' })).toBeInTheDocument()
  })
})
