/**
 * 묶음 패널 — **화면이 방법 목록을 적어 두지 않는가.**
 *
 * 무는 자리를 여기로 고른 이유: 표가 그려지는 것은 눈에 보이지만, **화면이
 * 목록을 적어 두는 것**은 안 보인다. 그러면 새 물성을 붙일 때 화면도 고쳐야
 * 하고, 그게 「확장이 아닌 상태」의 정확한 모양이다(D7).
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupsPanel } from '@/modules/materials/GroupsPanel'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'

/** 두 패널은 카드를 만든 뒤 `/cards` 로 가므로 라우터 안에서 그린다. */
function show(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

const kinds = vi.fn()
const ofMaterial = vi.fn()
const create = vi.fn()
const updateNote = vi.fn()
const remove = vi.fn()
const runs = vi.fn()

vi.mock('@/modules/materials/api.groups', () => ({
  groupsApi: {
    updateNote: (...args: unknown[]) => updateNote(...args),
    remove: (...args: unknown[]) => remove(...args),
    kinds: () => kinds(),
    ofMaterial: (...args: unknown[]) => ofMaterial(...args),
    create: (...args: unknown[]) => create(...args),
  },
}))

const createRateCard = vi.fn()
const createViscoelastic = vi.fn()
vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    createRateCard: (...args: unknown[]) => createRateCard(...args),
    createViscoelastic: (...args: unknown[]) => createViscoelastic(...args),
    // 카드 대화상자가 물려받을 밀도·푸아송비를 묻는다.
    inherited: () => Promise.resolve([]),
  },
}))

vi.mock('@/modules/tests/api', () => ({
  testsApi: { runs: (...args: unknown[]) => runs(...args) },
}))

const SPEC = {
  id: 'viscoelastic.prony_group',
  label: '묶음 Prony',
  // **실제 시험종류 key 다.** 후보 목록이 이걸로 걸러진다 — 안 맞으면 아무
  // 시험도 안 뜬다(2026-08-30, `dma_temperature_sweep` 이 그랬다).
  applies_to: ['dma_sweep'],
  params: [
    {
      name: 'method',
      label: '적합 방법',
      type: 'choice',
      default: 'pooled',
      choices: ['pooled', 'averaged', 'representative'],
      // **값은 안 바꾼다** — 저장되고 결과 스냅샷에도 남는 계약이다.
      choice_labels: {
        pooled: '한 번에 적합',
        averaged: '시편별 적합 후 평균',
        representative: '대표 하나 선택',
      },
      choice_help: {
        pooled: '시편들의 점을 모두 모아 한 번에 맞춥니다.',
        averaged: '시편마다 맞춘 뒤 계수를 평균합니다.',
        representative: '시편 하나의 계수를 그대로 씁니다.',
      },
      help: '여러 시편의 마스터커브에서 계수 한 벌을 구하는 방법입니다.',
    },
    { name: 'terms', label: '항 수', type: 'int', default: 0, choices: [], help: null },
    {
      name: 'representative',
      label: '대표 시편',
      type: 'str',
      default: '',
      choices: [],
      help: '비우면 잔차가 가장 작은 시편을 씁니다.',
    },
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
    // **마스터커브가 있어야 후보다** — 글로벌 피팅이 그것을 겹쳐 계수를 낸다.
    {
      id: 'r1',
      record_name: 'A_TEN_01',
      test_type_key: 'dma_sweep',
      test_type_label: 'DMA',
      master_curve_count: 1,
    },
    {
      id: 'r2',
      record_name: 'B_TEN_01',
      test_type_key: 'dma_sweep',
      test_type_label: 'DMA',
      master_curve_count: 1,
    },
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
    show(<GroupsPanel materialId="m1" />)
    expect(await screen.findByText(/고른 3건 · 쓴 1건/)).toBeInTheDocument()
  })

  it('값의 이름과 단위를 서버가 준 대로 쓴다', async () => {
    // 라벨에 손으로 적으면 표만 바꿨을 때 옛 단위를 적은 채 새 값을 받는다.
    show(<GroupsPanel materialId="m1" />)
    expect(await screen.findByText('평형 탄성률')).toBeInTheDocument()
  })

  it('감수한 것을 적는다', async () => {
    show(<GroupsPanel materialId="m1" />)
    expect(await screen.findByText(/대표로 골랐습니다/)).toBeInTheDocument()
  })
})

describe('글로벌 피팅', () => {
  it('방법 목록을 서버에서 받아 그린다', async () => {
    /** **이것이 확장의 요점이다.** 화면이 적어 두면 새 방법이 생겨도 안 보인다. */
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))

    const picker = await screen.findByLabelText('적합 방법')
    // **값은 서버 것 그대로, 보이는 이름만 사람 말로.**
    expect([...picker.querySelectorAll('option')].map((one) => one.value)).toEqual([
      'pooled',
      'averaged',
      'representative',
    ])
    // **원래 값도 괄호로.** 논문·결과 스냅샷에는 `pooled` 로 남는다.
    // **추천은 서버가 준 기본값**이다 — 화면이 따로 안 적는다.
    expect([...picker.querySelectorAll('option')].map((one) => one.textContent)).toEqual([
      '한 번에 적합 (pooled) · 추천',
      '시편별 적합 후 평균 (averaged)',
      '대표 하나 선택 (representative)',
    ])
  })

  it('둘 미만이면 못 누른다', async () => {
    // 하나를 「묶었다」 고 부르면 나중에 묶음인지 한 건인지 구별할 수 없다.
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))

    await userEvent.click(await screen.findByLabelText('A_TEN_01 선택'))
    expect(screen.getByRole('button', { name: /시편 1건 적합/ })).toBeDisabled()
  })

  it('고른 것만 보낸다', async () => {
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))

    await userEvent.click(await screen.findByLabelText('A_TEN_01 선택'))
    await userEvent.click(screen.getByLabelText('B_TEN_01 선택'))
    await userEvent.click(screen.getByRole('button', { name: /시편 2건 적합/ }))

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
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))

    // **입력칸이 아니라 고르는 칸이다**(2026-08-30) — 몇 항을 적어야 하는지
    // 사람이 알 길이 없어서 목록으로 바꿨다. `0` 은 「자동」 이라고 적는다.
    await userEvent.selectOptions(await screen.findByLabelText('항 수'), '3')
    await userEvent.click(screen.getByLabelText('A_TEN_01 선택'))
    await userEvent.click(screen.getByLabelText('B_TEN_01 선택'))
    await userEvent.click(screen.getByRole('button', { name: /시편 2건 적합/ }))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ options: expect.objectContaining({ terms: 3 }) })
      )
    )
  })
})

describe('쓰기 쉽게', () => {
  const open = async () => {
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))
  }

  it('고른 방법의 설명만 보인다', async () => {
    // **셋을 한 줄에 이어 적으면** 지금 무엇을 고른 것인지 눈으로 찾아야 한다.
    await open()
    expect(await screen.findByText(/시편들의 점을 모두 모아/)).toBeInTheDocument()
    expect(screen.queryByText(/시편마다 맞춘 뒤 계수를 평균/)).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('적합 방법'), 'averaged')
    expect(await screen.findByText(/시편마다 맞춘 뒤 계수를 평균/)).toBeInTheDocument()
    expect(screen.queryByText(/시편들의 점을 모두 모아/)).not.toBeInTheDocument()
  })

  it('방법 이름을 사람 말로 보인다', async () => {
    // **값은 안 바꾼다** — `pooled` 는 저장되고 결과 스냅샷에도 남는 계약이다.
    await open()
    expect(
      await screen.findByRole('option', { name: /한 번에 적합 \(pooled\)/ })
    ).toBeInTheDocument()
  })

  it('대표 시편 칸은 그 방법일 때만 뜬다', async () => {
    // 늘 보이면 무엇을 적어야 하는지 매번 생각하게 된다.
    await open()
    await screen.findByLabelText('적합 방법')
    expect(screen.queryByLabelText('대표 시편')).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('적합 방법'), 'representative')
    expect(await screen.findByLabelText('대표 시편')).toBeInTheDocument()
  })

  it('대표 시편은 고른 것 중에서 고른다', async () => {
    // **이름을 손으로 적게 하지 않는다** — 오타 하나면 서버가 못 찾는다.
    await open()
    await userEvent.click(await screen.findByLabelText('A_TEN_01 선택'))
    await userEvent.selectOptions(screen.getByLabelText('적합 방법'), 'representative')
    const box = await screen.findByLabelText('대표 시편')
    expect(within(box).getByRole('option', { name: 'A_TEN_01' })).toBeInTheDocument()
    // 안 고른 것은 대표가 될 수 없다.
    expect(within(box).queryByRole('option', { name: 'B_TEN_01' })).not.toBeInTheDocument()
  })

  it('항 수 0 을 「자동」 이라고 적는다', async () => {
    // **숫자 0 은 「항이 없다」 로 읽힌다** — 실제로는 「알아서 고르라」 다.
    await open()
    const box = await screen.findByLabelText('항 수')
    expect(within(box).getByRole('option', { name: /자동/ })).toBeInTheDocument()
  })

  it('무엇이 나오는지 먼저 말한다', async () => {
    await open()
    // 목록에서 이름이 이어져 나온다 — `makes_values` 가 준다.
    expect(await screen.findByText(/평형 탄성률 · 항 수/)).toBeInTheDocument()
  })

  it('쓸 수 없는 시험은 목록에 없다', async () => {
    // **누르기 전에 알 수 있는 것을 눌러 보고 알게 하지 않는다.**
    runs.mockResolvedValue({
      items: [
        {
          id: 'r1',
          record_name: 'DMA_01',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 1,
        },
        {
          id: 'r9',
          record_name: 'TENSILE_01',
          test_type_key: 'tensile',
          test_type_label: '인장',
          master_curve_count: 0,
        },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    })
    await open()
    expect(await screen.findByLabelText('DMA_01 선택')).toBeInTheDocument()
    expect(screen.queryByLabelText('TENSILE_01 선택')).not.toBeInTheDocument()
  })

  it('왜 이것만 뜨는지 말한다', async () => {
    // 아무 말 없이 걸러 두면 「내 시험이 왜 없지」 가 된다.
    await open()
    expect(await screen.findByText(/마스터커브가 있는 시험만 표시/)).toBeInTheDocument()
  })
})

describe('마스터커브가 있어야 후보다', () => {
  /**
   * **시험종류만으로는 못 거른다** (2026-08-30).
   *
   * 온도 스윕과 변형률 스윕이 둘 다 `dma_sweep` 인데, 마스터커브는 온도 스윕에서만
   * 나온다 — 변형률 스윕은 **애초에 만들 수 없는** 것이라 종류로 거르면 그대로
   * 남고, 골라 보고서야 거절당한다.
   */
  const open = async () => {
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))
  }

  it('마스터커브가 없으면 목록에 없다', async () => {
    runs.mockResolvedValue({
      items: [
        {
          id: 'r1',
          record_name: 'TEMP_SWEEP',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 1,
        },
        {
          // 변형률 스윕 — 종류는 같지만 겹칠 것이 없다.
          id: 'r2',
          record_name: 'STRAIN_SWEEP',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 0,
        },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    })
    await open()
    expect(await screen.findByLabelText('TEMP_SWEEP 선택')).toBeInTheDocument()
    expect(screen.queryByLabelText('STRAIN_SWEEP 선택')).not.toBeInTheDocument()
  })

  it('몇 건이 왜 빠졌는지 말한다', async () => {
    // **그 수가 다음 할 일을 가리킨다** — 겹쳐서 만들면 그것도 쓸 수 있다.
    // 온도가 여러 단인 것만 그렇게 말한다: 한 단짜리는 겹칠 상대가 없다.
    runs.mockResolvedValue({
      items: [
        {
          id: 'r1',
          record_name: 'A',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 1,
        },
        {
          id: 'r2',
          record_name: 'B',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 0,
          temperature_step_count: 6,
        },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    })
    await open()
    expect(await screen.findByText(/1건은 미겹침으로 제외/)).toBeInTheDocument()
  })

  it('겹칠 수 없는 시험은 「안 겹쳤다」 고 말하지 않는다', async () => {
    // **변형률 스윕은 온도가 한 단이라 겹칠 상대가 없다.** 「만들면 쓸 수 있다」 고
    // 적으면 할 수 없는 일을 시키는 셈이다.
    runs.mockResolvedValue({
      items: [
        {
          id: 'r1',
          record_name: 'A',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 1,
          temperature_step_count: 6,
        },
        {
          id: 'r2',
          record_name: 'B',
          test_type_key: 'dma_sweep',
          test_type_label: 'DMA',
          master_curve_count: 0,
          temperature_step_count: 1,
        },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    })
    await open()
    expect(await screen.findByText(/온도 한 단으로 겹치기 불가/)).toBeInTheDocument()
    expect(screen.queryByText(/미겹침으로 제외/)).not.toBeInTheDocument()
  })

  it('빠진 것이 없으면 그 말을 안 한다', async () => {
    // **없는 문제를 말하면 다음부터 안 읽는다.**
    await open()
    await screen.findByLabelText('A_TEN_01 선택')
    expect(screen.queryByText(/제외/)).not.toBeInTheDocument()
  })
})

describe('언제 쓰는 것인지', () => {
  /**
   * **머리글은 「무엇을 하나」 가 아니라 「언제 쓰나」 를 말한다.**
   *
   * 계산의 정의는 방법을 고른 뒤 그 설명이 한다. 그리고 「한 번에 적합」 은 세
   * 방법 중 하나(pooled)의 설명이라, 머리글에 적으면 나머지 둘에는 틀린 말이 된다.
   */
  it('왜 필요한지 적는다', async () => {
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))
    expect(await screen.findByText(/Prony 계수 한 벌 산출/)).toBeInTheDocument()
  })

  it('안 해도 되는 경우를 적는다', async () => {
    // **시편이 하나면 이 계산이 필요 없다** — 그것을 안 적으면 「해야 하는 것」 으로
    // 읽히고, 한 건짜리에도 들어와 둘 미만이라 못 누르는 것을 보게 된다.
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))
    expect(await screen.findByText(/시편이 하나뿐이면 불필요/)).toBeInTheDocument()
  })

  it('방법 하나의 설명을 머리글에 안 적는다', async () => {
    // 「한 번에 적합」 은 pooled 의 설명이다 — 머리글에 있으면 averaged 를 골라도
    // 그 말이 남아 있어 무엇이 맞는지 흐려진다.
    show(<GroupsPanel materialId="m1" />)
    await screen.findByText(/고른 3건/)
    await userEvent.click(screen.getByRole('button', { name: '글로벌 피팅' }))
    const dialog = await screen.findByRole('dialog')
    const head = dialog.querySelector('[data-slot="dialog-description"]')
    expect(head?.textContent).not.toMatch(/한 번에 적합/)
  })
})

describe('후보의 조건은 서버가 말한다', () => {
  /**
   * `needs` — Prony 는 마스터커브가 있는 시험만, 속도별 묶음은 채택된 처리 결과가
   * 있는 시험만 후보다. 화면이 플러그인 id 로 알아맞히면 새 묶음마다 화면을 고쳐야
   * 한다. 그리고 **왜 빠졌는지**도 조건에 맞는 말로 적어야 한다.
   */
  const RATE_SPEC = {
    ...SPEC,
    id: 'tensile.rate_family',
    label: '속도별 소성 곡선',
    applies_to: ['tensile'],
    needs: 'adopted_result',
    params: [
      { name: 'bin_ratio', label: '같은 속도로 볼 폭', type: 'float', default: 0.3, choices: [], help: '' },
    ],
    makes_values: [{ key: 'rate_count', label: '속도 묶음 수', si_unit: '1' }],
  }

  it('채택된 결과가 있는 시험만 후보이고, 빠진 이유를 그 말로 적는다', async () => {
    kinds.mockResolvedValue([RATE_SPEC])
    runs.mockResolvedValue({
      items: [
        { id: 'r1', record_name: 'A_TEN_01', test_type_key: 'tensile', adopted_result_id: 'p1' },
        { id: 'r2', record_name: 'B_TEN_01', test_type_key: 'tensile', adopted_result_id: null },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    })
    show(<GroupsPanel materialId="m1" />)
    await userEvent.click(await screen.findByRole('button', { name: '글로벌 피팅' }))

    expect(await screen.findByLabelText('A_TEN_01 선택')).toBeInTheDocument()
    expect(screen.queryByLabelText('B_TEN_01 선택')).not.toBeInTheDocument()
    expect(screen.getByText(/채택된 처리 결과가 있는 시험만 표시/)).toBeInTheDocument()
    expect(screen.getByText(/1건은 미채택으로 제외/)).toBeInTheDocument()
    expect(screen.queryByText(/마스터커브가 있는 시험만/)).not.toBeInTheDocument()
  })

  it('실수 칸은 숫자로 보낸다', async () => {
    kinds.mockResolvedValue([RATE_SPEC])
    runs.mockResolvedValue({
      items: [
        { id: 'r1', record_name: 'A', test_type_key: 'tensile', adopted_result_id: 'p1' },
        { id: 'r2', record_name: 'B', test_type_key: 'tensile', adopted_result_id: 'p2' },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    })
    show(<GroupsPanel materialId="m1" />)
    await userEvent.click(await screen.findByRole('button', { name: '글로벌 피팅' }))
    await userEvent.type(await screen.findByLabelText('같은 속도로 볼 폭'), '0.5')
    await userEvent.click(screen.getByLabelText('A 선택'))
    await userEvent.click(screen.getByLabelText('B 선택'))
    await userEvent.click(screen.getByRole('button', { name: /시편 2건 적합/ }))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ plugin_id: 'tensile.rate_family', options: { bin_ratio: 0.5 } })
      )
    )
  })

  it('속도별 묶음에는 속도 표와 카드 단추가 선다', async () => {
    ofMaterial.mockResolvedValue([
      {
        ...ROW,
        id: 'g2',
        plugin_id: 'tensile.rate_family',
        options: {},
        used: ['A', 'B', 'C'],
        values: { rate_count: 2, reference_rate: 0.01 },
        detail: {
          model: 'none',
          rates: [
            { rate: 0.01, count: 2, members: ['A', 'B'], ratio_mean: 1 },
            { rate: 1, count: 1, members: ['C'], ratio_mean: 1.08 },
          ],
        },
        warnings: [],
      },
    ])
    kinds.mockResolvedValue([RATE_SPEC])
    show(<GroupsPanel materialId="m1" />)
    expect(await screen.findByRole('button', { name: /생성/ })).toBeInTheDocument()
    expect(screen.getByText('1.080')).toBeInTheDocument()
    expect(screen.getByText(/2속도/)).toBeInTheDocument()
  })

  it('설정 변경 후 재적합 — 그때의 방법·옵션·시편이 채워진 채 열리고, 새 결과를 만든다', async () => {
    // 숫자는 못 고친다(계산한 값이다). 대신 설정을 채운 모달에서 바꿔 다시 맞춘다.
    show(<GroupsPanel materialId="m1" />)
    await userEvent.click(await screen.findByRole('button', { name: /설정 변경 후 재적합/ }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('결과의 방법·옵션·시편을 채웠습니다')
    expect(within(dialog).getByLabelText('적합 계산')).toHaveValue(ROW.plugin_id)
    expect(within(dialog).getByLabelText('적합 방법')).toHaveValue('representative')
    // 그때 고른 시편이 켜져 있다.
    expect(within(dialog).getByLabelText('A_TEN_01 선택')).toBeChecked()
    expect(within(dialog).getByLabelText('B_TEN_01 선택')).toBeChecked()
    await userEvent.click(within(dialog).getByRole('button', { name: /건 적합/ }))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          plugin_id: ROW.plugin_id,
          run_ids: expect.arrayContaining(['r1', 'r2']),
          options: expect.objectContaining({ method: 'representative' }),
        })
      )
    )
  })

  it('메모를 고칠 수 있고, 값은 안 건드린다', async () => {
    updateNote.mockResolvedValue({ ...ROW, note: '상온 기준' })
    show(<GroupsPanel materialId="m1" />)
    await userEvent.click(await screen.findByRole('button', { name: '묶음 메모 편집' }))
    await userEvent.type(screen.getByLabelText('묶음 메모'), '상온 기준')
    await userEvent.click(screen.getByRole('button', { name: '메모 저장' }))
    await waitFor(() => expect(updateNote).toHaveBeenCalledWith(ROW.id, '상온 기준'))
  })

  it('지우기는 한 번 묻고 나서 부른다', async () => {
    remove.mockResolvedValue(undefined)
    show(<GroupsPanel materialId="m1" />)
    await userEvent.click(await screen.findByRole('button', { name: '묶음 삭제' }))
    expect(remove).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith(ROW.id))
  })

  it('Prony 묶음에는 점탄성 카드 단추가 서고, 묶음 id 로 만든다', async () => {
    // 서버는 `group_result_id` 를 받았는데 화면에 단추가 없었다(2026-09-05).
    createViscoelastic.mockResolvedValue({ id: 'c7', material_id: 'm1' })
    const onCardMade = vi.fn()
    show(<GroupsPanel materialId="m1" onCardMade={onCardMade} />)
    await userEvent.click(await screen.findByRole('button', { name: /^생성$/ }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('점탄성 카드 생성')
    await userEvent.click(within(dialog).getByRole('button', { name: '생성' }))
    await waitFor(() =>
      expect(createViscoelastic).toHaveBeenCalledWith(
        expect.objectContaining({ group_result_id: ROW.id })
      )
    )
    expect(onCardMade).toHaveBeenCalled()
  })

  it('카드 단추는 묻고 나서 만든다 — 묻지 않으면 누를 때마다 초안이 쌓인다', async () => {
    ofMaterial.mockResolvedValue([
      {
        ...ROW,
        id: 'g2',
        plugin_id: 'tensile.rate_family',
        options: {},
        used: ['A', 'B'],
        values: { rate_count: 2, reference_rate: 0.01 },
        detail: {
          model: 'none',
          rates: [
            { rate: 0.01, count: 1, members: ['A'], ratio_mean: 1 },
            { rate: 1, count: 1, members: ['B'], ratio_mean: 1.1 },
          ],
        },
        warnings: [],
      },
    ])
    kinds.mockResolvedValue([RATE_SPEC])
    createRateCard.mockResolvedValue({ id: 'c9', material_id: 'm1' })
    show(<GroupsPanel materialId="m1" />)

    await userEvent.click(await screen.findByRole('button', { name: /^생성$/ }))
    // 누르자마자 만들지 않는다.
    expect(createRateCard).not.toHaveBeenCalled()
    expect(await screen.findByRole('dialog')).toHaveTextContent('속도 의존 소성 카드 만들기')
    expect(screen.getByRole('dialog')).toHaveTextContent('속도 묶음 2개')

    await userEvent.click(screen.getByRole('button', { name: '생성' }))
    await waitFor(() =>
      expect(createRateCard).toHaveBeenCalledWith(
        expect.objectContaining({ group_result_id: 'g2', poisson_ratio: null, density: null })
      )
    )
  })
})
