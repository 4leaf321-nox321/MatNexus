/**
 * 표준 규격 가져오기 — **칸과 기호는 가져오고, 치수 값은 안 가져온다.**
 *
 * 근거 문서가 본문이 유료라 2차 출처 기반이고, 출처끼리 어긋난 곳이 실제로 있다
 * (D5766 전체 길이가 152 mm 와 250 mm 로). 그 숫자를 심으면 검증 안 된 값이
 * 시스템의 정본이 된다 — 치수는 자릿수 하나만 틀려도 응력이 통째로 어긋나는데
 * 숫자는 그럴듯해 보인다.
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
    value: 'ASTM E8/E8M 환봉',
    category: '인장',
    family: '금속 인장',
    fields: [field('gauge_length', '게이지 길이', 'G'), field('diameter', '직경', 'D')],
    cross_section: 'circle',
    ratio_checks: [],
    help: 'E8 은 게이지가 4D, E8M 은 5D 입니다.',
    taken: false,
  },
  {
    key: 'astm_e8_sheet',
    value: 'ASTM E8/E8M 박판형',
    category: '인장',
    family: '금속 인장',
    fields: [field('width', '평행부 폭', 'W')],
    cross_section: 'rectangle',
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
  it('숫자는 안 가져온다고 먼저 말한다', async () => {
    // **이 화면이 주는 것은 구조지 값이 아니다.**
    show()
    expect(await screen.findByText(/치수 값은 규격서를 보고 넣으세요/)).toBeInTheDocument()
  })

  it('기호를 가져오기 전에 보여 준다', async () => {
    // 같은 글자가 규격마다 다른 뜻이라(E8 의 D 는 직경, D638 의 D 는 그립 간
    // 거리) 무엇이 들어오는지 누르기 전에 아는 편이 낫다.
    show()
    expect(await screen.findByText(/게이지 길이 G · 직경 D/)).toBeInTheDocument()
  })

  it('이미 있는 것은 못 고른다', async () => {
    // **덮으면 사람이 넣어 둔 치수가 사라진다.**
    show()
    expect(await screen.findByLabelText('ASTM E8/E8M 박판형')).toBeDisabled()
    expect(screen.getByText('이미 있음')).toBeInTheDocument()
  })

  it('고른 것만 가져온다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByLabelText('ASTM E8/E8M 환봉'))
    await user.click(screen.getByRole('button', { name: /1개 가져오기/ }))

    await waitFor(() => expect(importStandards).toHaveBeenCalledWith(['astm_e8_round']))
    expect(await screen.findByText(/값을 넣으세요/)).toBeInTheDocument()
  })

  it('비율 조건이 몇 개인지 미리 보여 준다', async () => {
    // DMA 는 숫자를 안 주고 비만 주는 파트가 대부분이다.
    show()
    expect(await screen.findByText(/비율 조건 1개/)).toBeInTheDocument()
  })

  it('아무것도 안 골랐으면 못 누른다', async () => {
    show()
    await screen.findByLabelText('ASTM E8/E8M 환봉')
    expect(screen.getByRole('button', { name: /가져오기/ })).toBeDisabled()
  })
})
