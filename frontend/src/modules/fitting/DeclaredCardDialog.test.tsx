/**
 * 적어 둔 값만으로 카드 만들기 — **시험이 하나도 없는 재료의 길**(ADR 0016).
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   무엇이 실릴지 먼저 보인다   누른 뒤에 "없습니다" 를 보는 것은 늦다
 *   서버가 판정한다            화면이 선언 물성을 보고 나름대로 세지 않는다
 *   어디서 온 값인지 함께 본다   시료 실측 밀도와 문헌 탄성계수가 섞여 들어간다
 *   단위를 화면에 안 박는다     블록 선언이 값마다 저장 단위를 들고 있다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeclaredCardDialog } from '@/modules/fitting/DeclaredCardDialog'

const declaredPreview = vi.fn()
const createDeclaredCard = vi.fn()
const blocks = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    declaredPreview: (...args: unknown[]) => declaredPreview(...args),
    createDeclaredCard: (...args: unknown[]) => createDeclaredCard(...args),
    blocks: () => blocks(),
  },
}))

const BLOCKS = [
  {
    key: 'elastic',
    label: '탄성',
    help: null,
    in_deck: true,
    produces: [
      { key: 'youngs_modulus', label: '탄성계수', si_unit: 'Pa', help: null },
      { key: 'density', label: '밀도', si_unit: 'kg/m3', help: null },
    ],
    rows: [],
  },
  {
    key: 'thermal',
    label: '열물성',
    help: null,
    in_deck: true,
    produces: [
      { key: 'thermal_conductivity', label: '열전도도', si_unit: 'W/(m.K)', help: null },
    ],
    rows: [],
  },
]

const PREVIEW = {
  material_name: 'SECC_MDOI_1.0',
  blocks: ['elastic', 'thermal'],
  values: [
    {
      key: 'youngs_modulus',
      label: '탄성계수',
      value: 206e9,
      source: 'declared:literature',
      detail: '사람이 적은 값입니다 — ASM Handbook Vol.1 p.12.',
    },
    {
      key: 'density',
      label: '밀도',
      value: 7900,
      source: 'sample',
      // 서버가 실제로 내는 문장이다(`app/shared/display.density_text`).
      detail: '시료에서 잰 값입니다 (7.9e-09 tonne/mm3).',
    },
  ],
}

function dialog(onSaved = vi.fn()) {
  render(
    <DeclaredCardDialog materialId="m-1" open onClose={vi.fn()} onSaved={onSaved} />
  )
  return onSaved
}

beforeEach(() => {
  vi.clearAllMocks()
  declaredPreview.mockResolvedValue(PREVIEW)
  blocks.mockResolvedValue(BLOCKS)
  createDeclaredCard.mockResolvedValue({ id: 'c-1' })
})

describe('적어 둔 값으로 카드 만들기', () => {
  it('무엇이 실릴지 먼저 보인다', async () => {
    // **만들기를 누른 뒤에 "적어 둔 물성이 없습니다" 를 보는 것은 늦다.**
    dialog()
    expect(await screen.findByText('탄성계수')).toBeInTheDocument()
    expect(screen.getByText('밀도')).toBeInTheDocument()
  })

  it('어디서 온 값인지 함께 본다', async () => {
    // **시료 실측 밀도와 문헌 탄성계수가 한 카드에 섞여 들어간다.**
    dialog()
    expect(await screen.findByText(/ASM Handbook Vol.1 p.12/)).toBeInTheDocument()
    expect(screen.getByText(/시료에서 잰 값/)).toBeInTheDocument()
  })

  it('단위를 블록 선언에서 가져온다', async () => {
    // **화면이 물성의 단위를 알면 새 물성마다 여기를 고쳐야 한다.** 저장은
    // Pa 인데 206 GPa 를 `2.06e11 Pa` 로 적으면 아무도 안 읽는다 — 그 규칙은
    // `shared/units` 가 알고, 어느 값이 Pa 인지는 블록 선언이 안다.
    dialog()
    await waitFor(() => expect(screen.getByText('탄성계수')).toBeInTheDocument())
    expect(screen.getByText('206 GPa')).toBeInTheDocument()
  })

  it('선언이 없으면 단위를 지어내지 않는다', async () => {
    // **위 시험이 선언에서 왔다는 증거다.** 블록 목록이 비면 이 값은 Pa 인지
    // 모르는 숫자가 되고, 그것이 맞는 결과다 — 아는 척하면 그 단위가 곧
    // 거짓말이 된다.
    blocks.mockResolvedValue([])
    dialog()
    await waitFor(() => expect(screen.getByText('탄성계수')).toBeInTheDocument())
    expect(screen.queryByText('206 GPa')).not.toBeInTheDocument()
  })

  it('적어 둔 것이 없으면 만들기를 잠근다', async () => {
    // 서버도 422 로 막지만, **막힌다는 것을 누르기 전에 알아야 한다.**
    declaredPreview.mockResolvedValue({ ...PREVIEW, blocks: [], values: [] })
    dialog()
    await waitFor(() =>
      expect(screen.getByText(/적어 둔 물성이 없습니다/)).toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: '만들기' })).toBeDisabled()
  })

  it('비운 칸은 안 보낸다', async () => {
    // **재료·시료에 있으면 비워 둔다** — 두 곳에 적으면 어느 쪽이 맞는지
    // 판정할 근거가 없다.
    dialog()
    await waitFor(() => expect(screen.getByText('탄성계수')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '만들기' }))
    await waitFor(() => expect(createDeclaredCard).toHaveBeenCalled())
    expect(createDeclaredCard.mock.calls[0][0]).toMatchObject({
      material_id: 'm-1',
      poisson_ratio: null,
      density: null,
    })
  })

  it('넣은 값은 보낸다', async () => {
    dialog()
    await waitFor(() => expect(screen.getByText('탄성계수')).toBeInTheDocument())
    await userEvent.type(screen.getByLabelText('푸아송비'), '0.29')
    await userEvent.click(screen.getByRole('button', { name: '만들기' }))
    await waitFor(() => expect(createDeclaredCard).toHaveBeenCalled())
    expect(createDeclaredCard.mock.calls[0][0]).toMatchObject({ poisson_ratio: 0.29 })
  })
})
