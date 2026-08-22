/**
 * 표준 규격 가져오기 — **구조는 확실하고, 값은 시작점이다.**
 *
 * 값은 규격이 딱 정해 둔 것만 온다. 최소값(`R ≥ 25`)·범위·근사·재료가 정하는
 * 두께는 빈 칸으로 온다 — 최소값을 공칭으로 심으면 그 값이 그 규격의 치수인
 * 척하게 된다.
 *
 * 그 값도 정본은 아니다. 근거 문서가 본문이 유료라 2차 출처 기반이고, 출처끼리
 * 어긋난 곳이 실제로 있다(D5766 전체 길이가 152 mm 와 250 mm 로).
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StandardCatalogDialog } from '@/modules/vocabulary/StandardCatalogDialog'

const standardCatalog = vi.fn()
const importStandards = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: {
    standardCatalog: () => standardCatalog(),
    importStandards: (...args: unknown[]) => importStandards(...args),
  },
}))

const field = (key: string, label: string, symbol: string | null = null) => ({
  key,
  label,
  symbol,
  kind: 'number',
  choices: [],
  dimension: 'length',
  si_unit: 'm',
  is_required: false,
  help: null,
  inherited: false,
})

const CATALOG = [
  {
    key: 'astm_e8_round',
    value: 'ASTM E8M 환봉 (12.5 mm)',
    category: '인장',
    family: '금속 인장',
    fields: [field('gauge_length', '게이지 길이', 'G'), field('diameter', '직경', 'D')],
    cross_section: 'circle',
    attributes: { diameter: 0.0125, gauge_length: 0.0625 },
    ratio_checks: [],
    help: 'E8M 미터계 표준입니다.',
    taken: false,
  },
  {
    key: 'astm_e8_sheet',
    value: 'ASTM E8/E8M 박판형',
    category: '인장',
    family: '금속 인장',
    fields: [field('width', '평행부 폭', 'W')],
    cross_section: 'rectangle',
    attributes: {},
    ratio_checks: [],
    help: null,
    taken: true,
  },
  {
    key: 'iso_6721_3',
    value: 'ISO 6721-3 (굽힘 공진)',
    category: 'DMA',
    family: 'DMA',
    fields: [field('length', '길이')],
    cross_section: null,
    attributes: {},
    ratio_checks: [
      { numerator: 'length', denominator: 'thickness', minimum: 50, maximum: null, help: null },
    ],
    help: null,
    taken: false,
  },
]

function show() {
  render(<StandardCatalogDialog onClose={() => {}} onImported={() => {}} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  standardCatalog.mockResolvedValue(CATALOG)
  importStandards.mockResolvedValue([{ id: 'new-1' }])
})

describe('표준 규격 가져오기', () => {
  it('값은 시작점이지 정본이 아니라고 먼저 말한다', async () => {
    // 근거가 2차 출처다. 그대로 믿으면 검증 안 된 값이 정본이 된다.
    show()
    expect(await screen.findByText(/값은 시작점이지 정본이 아닙니다/)).toBeInTheDocument()
  })

  it('값이 몇 개 오는지 보여 준다', async () => {
    // **값이 오는지 아닌지가 고르는 판단을 바꾼다** — 값이 없는 규격은
    // 가져와도 숫자를 다 넣어야 한다.
    show()
    expect(await screen.findByText(/값 2개 포함/)).toBeInTheDocument()
    expect(screen.getAllByText(/값 없음/).length).toBeGreaterThan(0)
  })

  it('기호를 가져오기 전에 보여 준다', async () => {
    // 같은 글자가 규격마다 다른 뜻이라(E8 의 D 는 직경, D638 의 D 는 그립 간
    // 거리) 무엇이 들어오는지 누르기 전에 아는 편이 낫다.
    show()
    expect(await screen.findByText(/게이지 길이 G · 직경 D/)).toBeInTheDocument()
  })

  it('이미 있는 것은 다른 이름을 받고서야 가져간다', async () => {
    // **이 기능이 가장 값을 하는 자리.** 같은 규격을 부서가 자기 치수로 쓰는
    // 경우다 — 규격서가 범위나 최소만 주는 칸이 많아 실제 값이 부서마다 갈린다.
    // 다만 이름이 같으면 시편에 붙은 이름만 보고 어느 것인지 알 수 없다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByLabelText('ASTM E8/E8M 박판형'))

    // 이름을 안 적으면 못 누른다.
    expect(screen.getByRole('button', { name: /1개 가져오기/ })).toBeDisabled()

    await user.type(
      screen.getByLabelText('ASTM E8/E8M 박판형 새 이름'),
      'ASTM E8 박판형 (사내 A)'
    )
    await user.click(screen.getByRole('button', { name: /1개 가져오기/ }))

    await waitFor(() =>
      expect(importStandards).toHaveBeenCalledWith([
        { key: 'astm_e8_sheet', value: 'ASTM E8 박판형 (사내 A)' },
      ])
    )
  })

  it('이미 있다는 것과 이름이 필요하다는 것을 함께 말한다', async () => {
    show()
    expect(await screen.findByText('이미 있음 · 다른 이름 필요')).toBeInTheDocument()
  })

  it('고른 것만 가져온다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByLabelText('ASTM E8M 환봉 (12.5 mm)'))
    await user.click(screen.getByRole('button', { name: /1개 가져오기/ }))

    await waitFor(() => expect(importStandards).toHaveBeenCalledWith([{ key: 'astm_e8_round' }]))
    expect(await screen.findByText(/값을 확인하고/)).toBeInTheDocument()
  })

  it('비율 조건이 몇 개인지 미리 보여 준다', async () => {
    // DMA 는 숫자를 안 주고 비만 주는 파트가 대부분이다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('tab', { name: /DMA/ }))
    expect(await screen.findByText(/비율 조건 1개/)).toBeInTheDocument()
  })

  it('갈래마다 탭으로 나뉜다', async () => {
    // **세로로 스물여덟 줄을 늘어놓지 않는다.** 금속을 고르는 사람에게 DMA
    // 아홉 줄은 방해다.
    show()
    expect(await screen.findByRole('tab', { name: /금속 인장/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /DMA/ })).toBeInTheDocument()
    // 다른 탭의 줄은 안 보인다.
    expect(screen.queryByLabelText('ISO 6721-3 (굽힘 공진)')).not.toBeInTheDocument()
  })

  it('탭 이름이 그 갈래에서 몇 개 골랐는지 말한다', async () => {
    // **탭을 옮기면 앞서 고른 것이 안 보인다.** 그러면 "몇 개 가져오기" 의
    // 숫자와 눈앞이 어긋난다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByLabelText('ASTM E8M 환봉 (12.5 mm)'))
    expect(await screen.findByRole('tab', { name: '금속 인장 — 1개 중 1개 고름' })).toBeInTheDocument()
  })

  it('아무것도 안 골랐으면 못 누른다', async () => {
    show()
    await screen.findByLabelText('ASTM E8M 환봉 (12.5 mm)')
    expect(screen.getByRole('button', { name: /가져오기/ })).toBeDisabled()
  })

  it('갈래를 통째로 고른다', async () => {
    // **스물여덟 줄을 하나씩 누르게 하지 않는다.** 처음 도입할 때는 한 갈래를
    // 통째로 가져오는 것이 보통이다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: '금속 인장 묶음 고르기' }))

    // 이미 있는 박판형은 안 섞인다 — 골라 봐야 아무 일도 안 일어난다.
    await user.click(screen.getByRole('button', { name: /1개 가져오기/ }))
    await waitFor(() => expect(importStandards).toHaveBeenCalledWith([{ key: 'astm_e8_round' }]))
  })

  it('한 번 더 누르면 그 묶음이 풀린다', async () => {
    const user = userEvent.setup()
    show()
    const button = await screen.findByRole('button', { name: '금속 인장 묶음 고르기' })
    await user.click(button)
    await user.click(await screen.findByRole('button', { name: '금속 인장 묶음 지우기' }))

    expect(screen.getByRole('button', { name: /가져오기/ })).toBeDisabled()
  })

  it('전체를 한 번에 고른다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: '전체 고르기' }))

    // 고를 수 있는 것은 둘이다(박판형은 이미 있음).
    await user.click(screen.getByRole('button', { name: /2개 가져오기/ }))
    await waitFor(() =>
      expect(importStandards).toHaveBeenCalledWith([
        { key: 'astm_e8_round' },
        { key: 'iso_6721_3' },
      ])
    )
  })

  it('몇 개를 골랐는지 세어 준다', async () => {
    const user = userEvent.setup()
    show()
    expect(await screen.findByText(/고를 수 있는 것 2개/)).toBeInTheDocument()
    await user.click(screen.getByLabelText('ASTM E8M 환봉 (12.5 mm)'))
    expect(await screen.findByText(/1개 골랐습니다/)).toBeInTheDocument()
  })
})
