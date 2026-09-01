/**
 * 물성 표 위의 한 줄 — **재촉이 맞는가, 그리고 조용해야 할 때 조용한가.**
 *
 * 이 줄은 「점탄성을 통째로 건너뛴 것」 을 드러내려고 있다. 그런데 잘못 세면 할 수
 * 없는 일을 시키고, 상관없는 재료(인장만 있는 것)에서 떠들면 소음이 된다 — 둘 다
 * 한 번 겪으면 사람은 그 자리를 다시 안 읽는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MasterCurveNotice } from '@/modules/materials/MasterCurveNotice'

const kinds = vi.fn()
const runs = vi.fn()

vi.mock('@/modules/materials/api.groups', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api.groups')>()),
  groupsApi: { kinds: () => kinds() },
}))

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: { runs: () => runs() },
}))

const dma = (over: Record<string, unknown> = {}) => ({
  id: crypto.randomUUID(),
  test_type_key: 'dma_sweep',
  master_curve_count: 0,
  temperature_step_count: 6,
  ...over,
})

function show() {
  render(
    <MemoryRouter>
      <MasterCurveNotice materialId="m1" />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  kinds.mockResolvedValue([{ id: 'viscoelastic.prony_group', applies_to: ['dma_sweep'] }])
  runs.mockResolvedValue({ items: [dma()] })
})

describe('말해야 할 때', () => {
  it('안 겹친 시험 수를 적고 그 재료의 시험 목록으로 데려간다', async () => {
    // **탭만 바꿔 주면 안 겹친 시험을 시료 목록에서 다시 찾아야 한다** — 세어 준
    // 값을 도로 버리는 셈이다. 그 재료로 걸러진 목록을 연다.
    show()
    expect(await screen.findByText(/겹칠 수 있는데 아직 안 만든 시험/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '그 시험 보기' })).toHaveAttribute(
      'href',
      '/tests?material=m1'
    )
  })

  it('이미 만든 것도 함께 센다', async () => {
    runs.mockResolvedValue({ items: [dma({ master_curve_count: 1 }), dma()] })
    show()
    const line = await screen.findByLabelText('마스터커브 현황')
    expect(line.textContent).toMatch(/있는 시험 1건/)
    expect(line.textContent).toMatch(/아직 안 만든 시험 1건/)
  })
})

describe('조용해야 할 때', () => {
  it('DMA 가 하나도 없으면 아무 말도 안 한다', async () => {
    // 인장만 있는 재료다. 여기에 마스터커브 이야기를 띄우면 그 줄은 소음이다.
    runs.mockResolvedValue({ items: [dma({ test_type_key: 'tensile' })] })
    show()
    await waitFor(() => expect(runs).toHaveBeenCalled())
    expect(screen.queryByLabelText('마스터커브 현황')).toBeNull()
  })

  it('변형률 스윕만 있으면 재촉하지 않는다', async () => {
    // **온도가 한 단이라 겹칠 것이 없다.** 이것을 「아직 안 했다」 로 적으면 할 수
    // 없는 일을 가리키게 된다.
    runs.mockResolvedValue({ items: [dma({ temperature_step_count: 1 })] })
    show()
    await waitFor(() => expect(runs).toHaveBeenCalled())
    expect(screen.queryByLabelText('마스터커브 현황')).toBeNull()
  })

  it('겹친 것과 못 겹치는 것이 섞이면 못 겹치는 쪽은 뺐다고 적는다', async () => {
    runs.mockResolvedValue({
      items: [dma({ master_curve_count: 1 }), dma({ temperature_step_count: 1 })],
    })
    show()
    const line = await screen.findByLabelText('마스터커브 현황')
    expect(line.textContent).toMatch(/겹칠 수 없는 시험 1건은 뺐습니다/)
    expect(screen.queryByRole('link', { name: '그 시험 보기' })).toBeNull()
  })
})
