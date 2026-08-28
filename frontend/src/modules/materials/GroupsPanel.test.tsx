/**
 * 묶음 패널 — **화면이 방법 목록을 적어 두지 않는가.**
 *
 * 무는 자리를 여기로 고른 이유: 표가 그려지는 것은 눈에 보이지만, **화면이
 * 목록을 적어 두는 것**은 안 보인다. 그러면 새 물성을 붙일 때 화면도 고쳐야
 * 하고, 그게 「확장이 아닌 상태」의 정확한 모양이다(D7).
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupsPanel } from '@/modules/materials/GroupsPanel'

const kinds = vi.fn()
const ofMaterial = vi.fn()
const create = vi.fn()
const runs = vi.fn()

vi.mock('@/modules/materials/api.groups', () => ({
  groupsApi: {
    kinds: () => kinds(),
    ofMaterial: (...args: unknown[]) => ofMaterial(...args),
    create: (...args: unknown[]) => create(...args),
  },
}))

vi.mock('@/modules/tests/api', () => ({
  testsApi: { runs: (...args: unknown[]) => runs(...args) },
}))

const SPEC = {
  id: 'viscoelastic.prony_group',
  label: '묶음 Prony',
  applies_to: ['dma_temperature_sweep'],
  params: [
    {
      name: 'method',
      label: '묶는 방법',
      type: 'choice',
      default: 'pooled',
      choices: ['pooled', 'averaged', 'representative'],
      help: '흩어짐이 잔차에 남는다',
    },
    { name: 'terms', label: '항 수', type: 'int', default: 0, choices: [], help: null },
  ],
  makes_values: [
    { key: 'equilibrium_pa', label: '평형 탄성률', si_unit: 'Pa' },
    { key: 'term_count', label: '항 수', si_unit: '1' },
  ],
}

const ROW = {
  id: 'g1',
  material_id: 'm1',
  plugin_id: 'viscoelastic.prony_group',
  plugin_version: '1',
  options: { method: 'representative' },
  members: [
    { test_run_id: 'r1', label: 'A_TEN_01' },
    { test_run_id: 'r2', label: 'B_TEN_01' },
    { test_run_id: 'r3', label: 'C_TEN_01' },
  ],
  used: ['A_TEN_01'],
  values: { equilibrium_pa: 5.0e6, term_count: 3 },
  detail: { method: 'representative', terms: [{}, {}, {}] },
  warnings: ['잔차가 가장 작은 A_TEN_01 을 대표로 골랐습니다.'],
  note: null,
  created_at: '2026-08-28T00:00:00Z',
}

const RUNS = {
  items: [
    { id: 'r1', record_name: 'A_TEN_01', test_type_label: 'DMA' },
    { id: 'r2', record_name: 'B_TEN_01', test_type_label: 'DMA' },
  ],
  total: 2,
  limit: 200,
  offset: 0,
}

beforeEach(() => {
  kinds.mockReset()
  ofMaterial.mockReset()
  create.mockReset()
  runs.mockReset()
  kinds.mockResolvedValue([SPEC])
  ofMaterial.mockResolvedValue([ROW])
  runs.mockResolvedValue(RUNS)
  create.mockResolvedValue(ROW)
})

describe('묶음 목록', () => {
  it('고른 것과 쓴 것을 나란히 보인다', async () => {
    /**
     * **대표를 고르면 셋 중 하나만 쓴다.** 그 차이가 안 보이면 「셋을 묶었다」 가
     * 거짓말이 된다 — 서버가 둘을 따로 주는 이유가 그것이다.
     */
    render(<GroupsPanel materialId="m1" />)
    expect(await screen.findByText(/고른 3건 · 쓴 1건/)).toBeInTheDocument()
  })

  it('값의 이름과 단위를 서버가 준 대로 쓴다', async () => {
    // 라벨에 손으로 적으면 표만 바꿨을 때 옛 단위를 적은 채 새 값을 받는다.
    render(<GroupsPanel materialId="m1" />)
    expect(await screen.findByText('평형 탄성률')).toBeInTheDocument()
  })

  it('감수한 것을 적는다', async () => {
    render(<GroupsPanel materialId="m1" />)
    expect(await screen.findByText(/대표로 골랐습니다/)).toBeInTheDocument()
  })
})

describe('새로 묶기', () => {
  it('방법 목록을 서버에서 받아 그린다', async () => {
    /** **이것이 확장의 요점이다.** 화면이 적어 두면 새 방법이 생겨도 안 보인다. */
    render(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: /새로 묶기/ }))

    const picker = await screen.findByLabelText('묶는 방법')
    expect([...picker.querySelectorAll('option')].map((one) => one.textContent)).toEqual([
      'pooled',
      'averaged',
      'representative',
    ])
  })

  it('둘 미만이면 못 누른다', async () => {
    // 하나를 「묶었다」 고 부르면 나중에 묶음인지 한 건인지 구별할 수 없다.
    render(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: /새로 묶기/ }))

    await userEvent.click(await screen.findByLabelText('A_TEN_01 고르기'))
    expect(screen.getByRole('button', { name: /1건 묶기/ })).toBeDisabled()
  })

  it('고른 것만 보낸다', async () => {
    render(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: /새로 묶기/ }))

    await userEvent.click(await screen.findByLabelText('A_TEN_01 고르기'))
    await userEvent.click(screen.getByLabelText('B_TEN_01 고르기'))
    await userEvent.click(screen.getByRole('button', { name: /2건 묶기/ }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          plugin_id: 'viscoelastic.prony_group',
          run_ids: ['r1', 'r2'],
        })
      )
    )
  })

  it('숫자 칸은 숫자로 보낸다', async () => {
    // 서버가 `int` 를 기대한다. 글자로 보내면 422 가 나는데 화면은 이유를 모른다.
    render(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: /새로 묶기/ }))

    await userEvent.type(await screen.findByLabelText('항 수'), '3')
    await userEvent.click(screen.getByLabelText('A_TEN_01 고르기'))
    await userEvent.click(screen.getByLabelText('B_TEN_01 고르기'))
    await userEvent.click(screen.getByRole('button', { name: /2건 묶기/ }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ options: expect.objectContaining({ terms: 3 }) })
      )
    )
  })
})
