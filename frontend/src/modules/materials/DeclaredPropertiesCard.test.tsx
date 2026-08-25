/**
 * 선언 물성 편집 — **시험이 주지 않는 값을 사람이 적는다**(ADR 0016).
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   항목을 코드에 안 박는다   기준정보가 정한다. 목록이 비면 그렇다고 말한다
 *   차원이 맞는 단위만 뜬다   비열 자리에 W/(m.K) 가 보이면 안 된다
 *   적은 단위로 되돌려 보인다  `2.06e11` 로 보이면 자기가 적은 값인지 모른다
 *   한 항목은 한 줄           이미 적은 항목은 추가 목록에서 사라진다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeclaredPropertiesCard } from '@/modules/materials/DeclaredPropertiesCard'

const propertyItems = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    propertyItems: (...args: unknown[]) => propertyItems(...args),
  },
}))

// **항목이 자기 단위를 들고 온다.** 차원으로 거르는 일은 서버가 한다 —
// 화면이 하면 그 규칙이 두 곳에 생기고, 갈라지는 날 비열 자리에 W/(m.K) 가 뜬다.
const ITEMS = [
  {
    item: '탄성계수',
    dimension: 'stress',
    si_unit: 'Pa',
    symbol: 'E',
    units: ['Pa', 'MPa', 'GPa'],
  },
  {
    item: '비열',
    dimension: 'specific_heat',
    si_unit: 'J/(kg.K)',
    symbol: 'Cp',
    units: ['J/(kg.K)', 'kJ/(kg.K)'],
  },
  {
    item: '열전도도',
    dimension: 'thermal_conductivity',
    si_unit: 'W/(m.K)',
    symbol: 'k',
    units: ['W/(m.K)'],
  },
]


function panel(rows: unknown[] = [], onSave = vi.fn().mockResolvedValue(undefined)) {
  render(
    <DeclaredPropertiesCard
      level="재료"
      rows={rows as never}
      onSave={onSave}
    />
  )
  return onSave
}

const DECLARED_E = {
  item: '탄성계수',
  // **되돌린 값도 서버가 준다.** 화면이 나눗셈을 하면 그 규칙이 두 곳에 생긴다.
  points: [{ value_si: 206e9, value: 206, temperature_k: null }],
  input_unit: 'GPa',
  source: 'literature',
  reference: 'KS D 3512 표 3',
  temperature_k: null,
  note: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  propertyItems.mockResolvedValue(ITEMS)
})

describe('선언 물성 편집', () => {
  it('적은 단위로 되돌려 보인다', async () => {
    // **저장은 SI 지만 `2.06e11` 로 보이면 자기가 적은 값인지 알기 어렵다.**
    panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    expect(screen.getByDisplayValue('KS D 3512 표 3')).toBeInTheDocument()
  })

  it('차원이 맞는 단위만 고르게 한다', async () => {
    // **비열 자리에 W/(m.K) 를 넣으면 값은 멀쩡한데 뜻이 다르다.** 서버도
    // 막지만, 고를 수 있게 두면 사람이 저장을 눌러 보고서야 안다.
    panel([
      {
        ...DECLARED_E,
        item: '비열',
        points: [{ value_si: 462, value: 462, temperature_k: null }],
        input_unit: 'J/(kg.K)',
      },
    ])
    await waitFor(() => expect(screen.getByDisplayValue('462')).toBeInTheDocument())
    await userEvent.click(screen.getByLabelText('단위'))
    // 목록이 실제로 열린 것을 먼저 확인한다 — 안 열린 채로 「없다」를 보면
    // 검사한 것이 아무것도 없다.
    expect(await screen.findByRole('option', { name: 'J/(kg.K)' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'W/(m.K)' })).not.toBeInTheDocument()
  })

  it('이미 적은 항목은 추가 목록에서 사라진다', async () => {
    // **한 항목은 한 줄이다.** 탄성계수가 두 줄이면 카드가 어느 것을 쓸지
    // 정할 수 없고, 그 판단을 여기서 안 하면 나중에 조용히 하나가 이긴다.
    panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('combobox', { name: '항목 추가' }))
    // **목록이 뜬 뒤에 본다.** 안 뜬 상태로 「없다」를 검사하면 무엇을 감췄든
    // 통과한다 — 아무것도 안 검사한 것과 같다.
    expect(await screen.findByRole('option', { name: /비열/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /탄성계수/ })).not.toBeInTheDocument()
  })

  it('항목이 하나도 없으면 어디에 등록하는지 말한다', async () => {
    // **"항목 추가가 안 뜬다" 로 끝나면 사람은 고장으로 읽는다.**
    propertyItems.mockResolvedValue([])
    panel()
    await waitFor(() =>
      expect(screen.getByText(/기준정보의/)).toHaveTextContent('물성 항목')
    )
  })

  it('고치기 전에는 저장을 못 누른다', async () => {
    panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()
    await userEvent.clear(screen.getByDisplayValue('206'))
    expect(screen.getByRole('button', { name: '저장' })).toBeEnabled()
  })

  it('적은 단위를 그대로 보낸다', async () => {
    // **환산 규칙이 두 곳에 있으면 언젠가 갈라진다**(ADR 0004). 화면은
    // `206 GPa` 를 보내고 서버가 SI 로 바꾼다.
    const onSave = panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.clear(screen.getByLabelText('탄성계수 값'))
    await userEvent.type(screen.getByLabelText('탄성계수 값'), '210')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect((onSave.mock.calls[0][0] as unknown[])[0]).toMatchObject({
      item: '탄성계수',
      points: [{ value: 210 }],
      input_unit: 'GPa',
    })
  })

  it('온도를 더해 표로 만든다', async () => {
    // **강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어진다.**
    // 열간 성형·용접·화재 해석은 그 곡선이 필요하다.
    const onSave = panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.type(screen.getByLabelText('탄성계수 온도'), '20')
    await userEvent.click(screen.getByRole('button', { name: '온도 추가' }))

    await userEvent.type(await screen.findByLabelText('탄성계수 값 2'), '170')
    await userEvent.type(screen.getByLabelText('탄성계수 온도 2'), '400')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect((onSave.mock.calls[0][0] as unknown[])[0]).toMatchObject({
      points: [
        { value: 206, temperature_k: 293.15 },
        { value: 170, temperature_k: 673.15 },
      ],
    })
  })

  it('점이 하나면 온도를 지우는 버튼이 없다', async () => {
    // **마지막 점까지 지우면 값 없는 항목이 된다** — 그것은 「이 물성이 있다」고
    // 말하는 거짓말이다. 줄 자체를 지우는 길은 따로 있다.
    panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    expect(
      screen.queryByRole('button', { name: /번째 온도를 지웁니다/ })
    ).not.toBeInTheDocument()
  })

  it('여럿이면 온도가 필수라고 미리 말한다', async () => {
    // 서버도 거절하지만, **누르기 전에 알려 주는 편이 낫다.**
    panel([
      {
        ...DECLARED_E,
        points: [
          { value_si: 206e9, value: 206, temperature_k: 293.15 },
          { value_si: 170e9, value: 170, temperature_k: 673.15 },
        ],
      },
    ])
    expect(await screen.findByText(/각각 어느 온도의 것인지/)).toBeInTheDocument()
    expect(screen.getByText(/끝값을 유지/)).toBeInTheDocument()
  })

  it('잰 온도는 ℃ 로 받아 K 로 보낸다', async () => {
    // **상온을 298 로 적는 사람은 없다.**
    const onSave = panel([DECLARED_E])
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.type(screen.getByLabelText('탄성계수 온도'), '20')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect((onSave.mock.calls[0][0] as unknown[])[0]).toMatchObject({
      points: [{ temperature_k: 293.15 }],
    })
  })
})
