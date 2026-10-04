/**
 * 한 번에 처리 — **시험 종류마다 따로, 곡선이 있는 것만**(ADR 0058).
 *
 * 레시피는 시험 종류의 것이다. 섞인 바구니에 인장 레시피를 통째로 걸면 DMA 건마다 실패하고,
 * 그 실패 스무 줄은 무엇을 고쳐야 하는지 말하지 않는다.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BatchByType } from '@/modules/processing/BatchPanel'

const overview = vi.fn()
const recipes = vi.fn()

vi.mock('@/modules/processing/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/processing/api')>()),
  processingApi: {
    overview: (...args: unknown[]) => overview(...args),
    recipes: (...args: unknown[]) => recipes(...args),
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
