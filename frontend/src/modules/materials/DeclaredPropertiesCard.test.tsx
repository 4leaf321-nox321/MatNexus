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

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeclaredPropertiesCard } from '@/modules/materials/DeclaredPropertiesCard'
import { display } from '@/shared/units'

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
    scales: [],
  },
  {
    item: '비열',
    dimension: 'specific_heat',
    si_unit: 'J/(kg.K)',
    symbol: 'Cp',
    units: ['J/(kg.K)', 'kJ/(kg.K)'],
    scales: [],
  },
  {
    item: '열전도도',
    dimension: 'thermal_conductivity',
    si_unit: 'W/(m.K)',
    symbol: 'k',
    units: ['W/(m.K)'],
    scales: [],
  },
  // **척도로 재는 물성.** 단위 자리에 척도 목록이 뜨고 환산이 없다.
  {
    item: '경도',
    dimension: 'dimensionless',
    si_unit: '1',
    symbol: 'H',
    units: [],
    scales: ['HV', 'HB', 'HRC'],
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

/**
 * 줄을 편다.
 *
 * **목록에서는 한 줄이다**(2026-08-30). 전에는 항목마다 편집 폼이 늘 펼쳐져
 * 있었는데, 한 항목이 세 줄이라 **여섯 개만 있어도 화면이 다 찼다** — 그런데 이
 * 카드에 가장 자주 하는 일은 「무엇이 적혀 있나」 를 보는 것이다.
 *
 * 아래 시험들은 **폼 안의 규칙**(단위 되돌리기·차원 검사·척도 칸)을 보는 것이라
 * 먼저 편다. 접힌 줄이 무엇을 보이는지는 `목록` 쪽에서 따로 문다.
 */
async function openFirst() {
  const user = userEvent.setup()
  const rows = await screen.findAllByRole('button', { name: /편집$/ })
  await user.click(rows[0])
  return user
}

/**
 * 편집 창을 닫는다.
 *
 * **창이 열려 있으면 뒤쪽이 `aria-hidden` 이라** 카드의 저장 단추에 손이 안
 * 닿는다 — 그것이 창을 쓰는 값이기도 하다(고치는 동안 다른 것을 못 누른다).
 * 저장을 누르는 시험은 먼저 닫는다.
 */
async function closeDialog(user: ReturnType<typeof userEvent.setup>) {
  if (!screen.queryByRole('dialog')) return
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
}

/**
 * 저장한다 — **창 안에서**(2026-08-30, A안).
 *
 * 전에는 창을 닫고 바깥의 저장을 눌렀는데, 값 목록이 물성 표로 옮겨 가면서
 * **고친 것이 어디에도 안 보이는** 상태가 생겼다 — 닫고 나면 바뀐 게 없어 보이고,
 * 저장 단추가 켜진 것을 스스로 알아채야 했다.
 */
async function saveCard() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '저장' }))
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
    await openFirst()
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
    await openFirst()
    // 목록이 온 뒤에 본다 — 오기 전에는 단위 후보가 적힌 것 하나뿐이라,
    // 「W/(m.K) 가 없다」가 **거르기 때문인지 안 왔기 때문인지** 알 수 없다.
    // **항목 목록이 온 뒤라야 거른 결과다.** 창 안의 단위 상자가 뜨는 것으로 안다.
    await screen.findByLabelText('단위')
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
    // **적어 둔 값은 곧바로 뜨지만 항목 목록은 나중에 온다.** 값이 보이는 것을
    // 기다린 뒤 트리거를 `getBy` 로 찾으면, 목록이 늦는 기계에서만 깨진다 —
    // 실제로 CI 에서만 그랬다.
    await userEvent.click(await screen.findByRole('combobox', { name: '선언 물성 추가' }))
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

  it('닫으면 고친 것이 사라진다', async () => {
    // **닫기가 곧 버리기다**(A안). 그러니 되돌릴 데가 있어야 한다 — 없으면 잘못
    // 고친 것을 손으로 다시 적어야 한다.
    const user = userEvent.setup()
    const onSave = panel([DECLARED_E])
    await openFirst()
    await user.clear(screen.getByDisplayValue('206'))
    await user.type(screen.getByLabelText('탄성계수 값'), '999')
    await user.click(screen.getByRole('button', { name: '취소' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(onSave).not.toHaveBeenCalled()
    await openFirst()
    expect(screen.getByDisplayValue('206')).toBeInTheDocument()
  })

  it('저장하면 창이 닫힌다', async () => {
    // 저장하고도 창이 남으면 「됐나?」 를 다시 확인하게 된다.
    const onSave = panel([DECLARED_E])
    await openFirst()
    await saveCard()
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('적은 단위를 그대로 보낸다', async () => {
    // **환산 규칙이 두 곳에 있으면 언젠가 갈라진다**(ADR 0004). 화면은
    // `206 GPa` 를 보내고 서버가 SI 로 바꾼다.
    const onSave = panel([DECLARED_E])
    await openFirst()
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.clear(screen.getByLabelText('탄성계수 값'))
    await userEvent.type(screen.getByLabelText('탄성계수 값'), '210')
    await saveCard()
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect((onSave.mock.calls[0][0] as unknown[])[0]).toMatchObject({
      item: '탄성계수',
      points: [{ value: 210 }],
      input_unit: 'GPa',
    })
  })

  it('온도 기호를 손으로 안 적는다 — 표에서 읽는다', async () => {
    // **표만 바꾸면 라벨이 옛 단위를 적은 채 새 값을 받는다**(AGENTS.md). 값은
    // 이미 표로 환산해 오므로, 기호만 손으로 적으면 둘이 갈린다.
    panel([
      {
        item: '탄성계수',
        points: [{ value_si: 170e9, value: 170, temperature_k: 673.15 }],
        input_unit: 'GPa',
        scale: null,
        source: 'datasheet',
        reference: 'MTC',
        note: null,
      },
    ])
    const shown = await screen.findByText(new RegExp(`@ .*${display('K', 'temperature').unit}`))
    expect(shown).toBeInTheDocument()
  })

  it('척도로 재는 물성은 단위 대신 척도를 고르게 한다', async () => {
    // **척도는 단위가 아니다.** `HV 200` 과 `HB 200` 은 다른 값이고 환산식이
    // 없다 — 단위 목록에 섞어 두면 사람이 MPa 를 고를 수 있게 된다.
    panel([
      {
        item: '경도',
        points: [{ value_si: 200, value: 200, temperature_k: null }],
        input_unit: null,
        scale: 'HV',
        source: 'datasheet',
        reference: 'MTC-2024-0812',
        note: null,
      },
    ])
    await openFirst()
    expect(await screen.findByLabelText('시험 척도')).toBeInTheDocument()
    expect(screen.queryByLabelText('단위')).not.toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('시험 척도'))
    expect(await screen.findByRole('option', { name: 'HB' })).toBeInTheDocument()
    // 단위는 하나도 안 뜬다.
    expect(screen.queryByRole('option', { name: 'MPa' })).not.toBeInTheDocument()
  })

  it('척도는 척도 칸으로 보낸다', async () => {
    // **단위 자리에 보내면 서버가 「모르는 단위」로 거절하고, 사람은 왜인지
    // 모른다.**
    const onSave = panel([
      {
        item: '경도',
        points: [{ value_si: 200, value: 200, temperature_k: null }],
        input_unit: null,
        scale: 'HV',
        source: 'datasheet',
        reference: 'MTC',
        note: null,
      },
    ])
    await openFirst()
    await waitFor(() => expect(screen.getByDisplayValue('200')).toBeInTheDocument())
    await userEvent.clear(screen.getByLabelText('경도 값'))
    await userEvent.type(screen.getByLabelText('경도 값'), '210')
    await saveCard()

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    const row = (onSave.mock.calls[0][0] as Record<string, unknown>[])[0]
    expect(row).toMatchObject({ item: '경도', scale: 'HV' })
    expect(row).not.toHaveProperty('input_unit')
  })

  it('항목 목록이 안 와도 척도는 척도 칸으로 간다', async () => {
    // **줄이 자기 성격을 든다.** 저장할 때 항목 목록을 다시 뒤지면, 목록이
    // 도착하기 전에 저장을 누른 사람이 척도를 단위 자리로 보내게 되고 서버가
    // 「모르는 단위」로 거절한다 — 사람은 왜인지 모른다.
    //
    // CI 에서 같은 뿌리의 흔들림이 났다: 값은 곧바로 뜨는데 목록은 나중에 온다.
    propertyItems.mockReturnValue(new Promise(() => {})) // 영영 안 온다
    const onSave = panel([
      {
        item: '경도',
        points: [{ value_si: 200, value: 200, temperature_k: null }],
        input_unit: null,
        scale: 'HV',
        source: 'datasheet',
        reference: 'MTC',
        note: null,
      },
    ])
    await openFirst()
    await waitFor(() => expect(screen.getByDisplayValue('200')).toBeInTheDocument())
    await userEvent.clear(screen.getByLabelText('경도 값'))
    await userEvent.type(screen.getByLabelText('경도 값'), '210')
    await saveCard()

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    const row = (onSave.mock.calls[0][0] as Record<string, unknown>[])[0]
    expect(row).toMatchObject({ item: '경도', scale: 'HV' })
    expect(row).not.toHaveProperty('input_unit')
  })

  it('보통 물성은 단위 칸으로 보낸다', async () => {
    const onSave = panel([DECLARED_E])
    await openFirst()
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.clear(screen.getByLabelText('탄성계수 값'))
    await userEvent.type(screen.getByLabelText('탄성계수 값'), '210')
    await saveCard()

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    const row = (onSave.mock.calls[0][0] as Record<string, unknown>[])[0]
    expect(row).toMatchObject({ input_unit: 'GPa' })
    expect(row).not.toHaveProperty('scale')
  })

  it('온도를 더해 표로 만든다', async () => {
    // **강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어진다.**
    // 열간 성형·용접·화재 해석은 그 곡선이 필요하다.
    const onSave = panel([DECLARED_E])
    await openFirst()
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.type(screen.getByLabelText('탄성계수 온도'), '20')
    await userEvent.click(screen.getByRole('button', { name: '온도 추가' }))

    await userEvent.type(await screen.findByLabelText('탄성계수 값 2'), '170')
    await userEvent.type(screen.getByLabelText('탄성계수 온도 2'), '400')
    await saveCard()

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
    await openFirst()
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
    await openFirst()
    expect(await screen.findByText(/각각 어느 온도의 것인지/)).toBeInTheDocument()
    expect(screen.getByText(/끝값을 유지/)).toBeInTheDocument()
  })

  it('잰 온도는 ℃ 로 받아 K 로 보낸다', async () => {
    // **상온을 298 로 적는 사람은 없다.**
    const onSave = panel([DECLARED_E])
    await openFirst()
    await waitFor(() => expect(screen.getByDisplayValue('206')).toBeInTheDocument())
    await userEvent.type(screen.getByLabelText('탄성계수 온도'), '20')
    await saveCard()
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect((onSave.mock.calls[0][0] as unknown[])[0]).toMatchObject({
      points: [{ temperature_k: 293.15 }],
    })
  })
})

describe('목록', () => {
  /**
   * **한 항목이 한 줄이다** (2026-08-30).
   *
   * 전에는 항목마다 편집 폼이 늘 펼쳐져 있었다. 한 항목이 단위·출처·값·근거로
   * 세 줄이라 **여섯 개만 있어도 화면이 다 찼고**, 「무엇이 적혀 있나」 를 보려고
   * 스크롤을 하게 됐다 — 이 카드에 가장 자주 하는 일이 그것인데.
   *
   * 접었으니 **접힌 줄이 답을 들고 있어야 한다.** 값을 보려고 매번 펴야 하면
   * 접은 뜻이 없다.
   */
  it('열지 않아도 값이 보인다', async () => {
    panel([DECLARED_E])
    const row = (await screen.findByText('탄성계수')).closest('tr') as HTMLElement
    // **단위는 값에 붙는다.** 열을 따로 두면 `206` 과 `GPa` 가 떨어져, 옆줄의
    // 단위와 짝을 맞춰 읽게 된다.
    expect(within(row).getByText(/206 GPa/)).toBeInTheDocument()
  })

  it('출처와 근거는 목록에 안 나온다', async () => {
    // **목록에서 하는 일은 「무엇이 얼마인가」 를 훑는 것**이고, 「어디서 왔나」 는
    // 그 값을 의심할 때 묻는다 — 늘 보이면 좁은 열에서 값이 밀린다.
    panel([DECLARED_E])
    const row = (await screen.findByText('탄성계수')).closest('tr') as HTMLElement
    expect(within(row).queryByText('문헌')).not.toBeInTheDocument()
    expect(within(row).queryByText('KS D 3512 표 3')).not.toBeInTheDocument()
    // 열 자체가 없어야 한다 — 헤더만 남으면 빈 칸이 자리를 먹는다.
    const heads = screen.getAllByRole('columnheader').map((one) => one.textContent)
    expect(heads).not.toContain('출처')
    expect(heads).not.toContain('근거 문서')
  })

  it('열면 출처와 근거가 있다', async () => {
    // 안 보이는 것과 없어진 것은 다르다.
    panel([DECLARED_E])
    await openFirst()
    expect(screen.getByDisplayValue('KS D 3512 표 3')).toBeInTheDocument()
    expect(screen.getByLabelText('출처')).toBeInTheDocument()
  })

  it('온도가 여럿이면 낱값을 다 적는다', async () => {
    // **줄여 놓으면 그 값이 얼마인지 보려고 매번 편집 창을 열어야 한다** —
    // 온도별 표를 적어 둔 이유가 그 값들인데.
    panel([
      {
        ...DECLARED_E,
        points: [
          { value_si: 206e9, value: 206, temperature_k: 293.15 },
          { value_si: 190e9, value: 190, temperature_k: 473.15 },
          { value_si: 170e9, value: 170, temperature_k: 673.15 },
        ],
      },
    ])
    const row = (await screen.findByText('탄성계수')).closest('tr') as HTMLElement
    expect(within(row).getByText(/206 GPa/)).toBeInTheDocument()
    expect(within(row).getByText(/190 GPa/)).toBeInTheDocument()
    expect(within(row).getByText(/170 GPa/)).toBeInTheDocument()
  })

  it('어느 온도의 값인지 함께 적는다', async () => {
    // **값만 셋 있으면 무엇이 다른지 모른다.** 온도가 그 표의 축이다.
    panel([
      {
        ...DECLARED_E,
        points: [
          { value_si: 206e9, value: 206, temperature_k: 293.15 },
          { value_si: 170e9, value: 170, temperature_k: 673.15 },
        ],
      },
    ])
    const row = (await screen.findByText('탄성계수')).closest('tr') as HTMLElement
    expect(within(row).getByText(/20 °C/)).toBeInTheDocument()
    expect(within(row).getByText(/400 °C/)).toBeInTheDocument()
  })

  it('한 번에 한 항목만 연다', async () => {
    // **창은 하나다.** 여럿이 펴져 있으면 표가 흔들리고 무엇을 고치는 중인지
    // 흐려진다 — 그것이 인라인 편집을 걷어낸 이유다.
    const user = userEvent.setup()
    panel([
      DECLARED_E,
      { ...DECLARED_E, item: '밀도', input_unit: 'g/cm^3', points: [{ value: 7.85 }] },
    ])
    await user.click(await screen.findByRole('button', { name: '탄성계수 편집' }))
    expect(screen.getByDisplayValue('206')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('7.85')).not.toBeInTheDocument()
  })

  it('연 창은 닫힌다', async () => {
    // **닫는 길이 분명해야 한다.** 줄 안에서 펼치던 때는 그것이 없었다.
    panel([DECLARED_E])
    const user = await openFirst()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await closeDialog(user)

    // 닫아도 표에는 값이 그대로 있다.
    const row = screen.getByText('탄성계수').closest('tr') as HTMLElement
    expect(within(row).getByText(/206 GPa/)).toBeInTheDocument()
  })

  it('여는 길이 하나다 — 줄 클릭과 단추가 섞이지 않는다', async () => {
    // 줄 전체가 눌리면서 그 안에 단추가 또 있으면, 어느 쪽을 눌러야 하는지
    // 매번 생각하게 된다.
    panel([DECLARED_E])
    const row = (await screen.findByText('탄성계수')).closest('tr') as HTMLElement
    expect(row.tagName).toBe('TR')
    expect(row.getAttribute('role')).not.toBe('button')
    expect(within(row).getByRole('button', { name: '탄성계수 편집' })).toBeInTheDocument()
  })
})

describe('유효숫자', () => {
  const LONG = {
    ...DECLARED_E,
    points: [{ value_si: 77.748477312e9, value: 77.748477312, temperature_k: null }],
  }

  it('표는 네 자리로 자른다', async () => {
    // **자리를 더 적는 것은 없는 정밀도를 주장하는 것이다.** 물성 실무의 관행이
    // 3~4자리다(ASTM E8 · ISO 6892).
    panel([LONG])
    const row = (await screen.findByText('탄성계수')).closest('tr') as HTMLElement
    expect(within(row).getByText(/77\.75 GPa/)).toBeInTheDocument()
  })

  it('편집 상자에는 적은 값이 그대로 있다', async () => {
    // **여기를 자르면 아무도 안 고쳤는데 값이 달라진다** — 자른 값이 상자에 뜨고,
    // 그대로 저장을 누르면 그 값이 저장된다. 읽는 자리와 고치는 자리는 다르다.
    panel([LONG])
    await openFirst()
    expect(screen.getByDisplayValue('77.748477312')).toBeInTheDocument()
  })

  it('고치지 않고 저장하면 값이 그대로 나간다', async () => {
    const onSave = panel([LONG])
    await openFirst()
    // 한 글자 고쳤다 되돌려 `dirty` 만 세운다.
    const user = userEvent.setup()
    const box = screen.getByDisplayValue('77.748477312')
    await user.type(box, '0')
    await user.clear(box)
    await user.type(box, '77.748477312')
    await saveCard()
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0][0].points[0].value).toBe(77.748477312)
  })
})

describe('편집 창의 차례', () => {
  /**
   * **차례가 곧 「무엇을 먼저 정하나」 다.**
   *
   *   지우기      값을 고치러 온 것이 아니라 항목을 걷으러 온 사람은 맨 위에서 끝난다.
   *   단위 → 값   단위를 먼저 정해야 값이 무슨 뜻인지 정해진다.
   *   출처 → 근거  「문헌」 을 고르고 나서 어느 핸드북인지 적는다 — 그 반대는 어색하다.
   */
  const order = (marks: string[]) => {
    const dialog = screen.getByRole('dialog')
    const text = dialog.textContent ?? ''
    return marks.map((one) => text.indexOf(one))
  }

  it('지우기가 맨 위다', async () => {
    panel([DECLARED_E])
    await openFirst()
    const [trash, unit] = order(['이 항목 지우기', '단위'])
    expect(trash).toBeGreaterThanOrEqual(0)
    expect(trash).toBeLessThan(unit)
  })

  it('단위가 값보다 앞이다', async () => {
    panel([DECLARED_E])
    await openFirst()
    const [unit, value] = order(['단위', '값'])
    expect(unit).toBeLessThan(value)
  })

  it('출처가 근거 문서 바로 위다', async () => {
    panel([DECLARED_E])
    await openFirst()
    const [value, source, reference] = order(['값', '출처', '근거 문서'])
    expect(value).toBeLessThan(source)
    expect(source).toBeLessThan(reference)
  })
})

describe('값 목록을 끌 수 있다', () => {
  /**
   * **재료 쪽은 끈다** (2026-08-30). 물성 요약이 잰 값과 함께 적은 값도 보이므로,
   * 여기서 또 보이면 **같은 값이 두 번** 나오고 그때 어느 쪽이 진짜인지 묻게 된다.
   *
   * 시료 쪽(밀시트)에는 그 요약이 없어 여기가 유일한 목록이다 — 그래서 기본은 켜짐.
   */
  it('끄면 값 목록이 없다', async () => {
    render(
      <DeclaredPropertiesCard
        level="재료"
        list={false}
        rows={[DECLARED_E] as never}
        onSave={vi.fn()}
      />
    )
    await screen.findByRole('combobox', { name: '선언 물성 추가' })
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/206 GPa/)).not.toBeInTheDocument()
  })

  it('꺼도 항목을 넣고 뺄 수는 있다', async () => {
    // **목록만 없앤 것이지 기능을 없앤 것이 아니다.**
    render(
      <DeclaredPropertiesCard
        level="재료"
        list={false}
        rows={[DECLARED_E] as never}
        onSave={vi.fn()}
      />
    )
    // **저장은 창 안에 있다** — 여기 남는 것은 넣는 자리 하나뿐이다.
    expect(await screen.findByRole('combobox', { name: '선언 물성 추가' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument()
  })

  it('기본은 켜짐이다', async () => {
    panel([DECLARED_E])
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })
})
