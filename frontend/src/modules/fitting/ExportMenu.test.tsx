/**
 * 내보내기 창 — **고르고, 보고, 받는다.**
 *
 * 전에는 메뉴에서 형식을 누르자마자 받았다(2026-10-04 바꿈). 이 파일이 보는 것:
 *
 *   1. 고른 계가 **배치 요청 · 내려받기 · 파일 이름에** 실리는가
 *   2. 목록을 **서버에서 받는가** — 화면이 적어 두면 계가 늘 때 뒤처진다
 *   3. 낼 수 없는 형식을 **미리** 막고 까닭을 말하는가
 *   4. 형식을 고르면 칸 배치와 덱 미리보기가 서고, 그 자리를 칠하는가
 *
 * ## 여기서 못 보는 것
 *
 * 「계를 고를 때 창이 안 닫히는가」 · 실제로 파일이 받아지는가는 진짜 브라우저가 본다
 * (`e2e/smoke.spec.ts`). jsdom 에서는 실패할 수가 없는 시험은 두지 않는다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExportMenu } from '@/modules/fitting/ExportMenu'
import type { DeckLayout, ExportFormat, PropertyCard } from '@/modules/fitting/api'

const download = vi.fn((..._args: unknown[]) => Promise.resolve())
const unitSystems = vi.fn()
const pairedFormats = vi.fn()
const layout = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    download: (...args: unknown[]) => download(...args),
    unitSystems: () => unitSystems(),
    pairedFormats: (...args: unknown[]) => pairedFormats(...args),
    layout: (...args: unknown[]) => layout(...args),
  },
}))

//: **기본이 첫 번째가 아니다.** 순서로 고르면 통과해 버려서, 그 시험이
//: `is_default` 를 실제로 보는지 알 수 없다.
const SYSTEMS = [
  {
    key: 'mm_n_tonne',
    label: 'mm · N · tonne (MPa)',
    declaration: 'tonne, mm, s, MPa',
    is_default: false,
  },
  { key: 'si', label: 'SI (kg · m · s · Pa)', declaration: 'kg, m, s, Pa', is_default: true },
]

const FORMATS = [
  {
    key: 'abaqus',
    label: 'Abaqus',
    extension: 'inp',
    describe: '*MATERIAL / *ELASTIC / *PLASTIC',
    requires: [],
  },
  {
    key: 'openradioss',
    label: 'OpenRadioss',
    extension: 'rad',
    describe: '/MAT/LAW36',
    requires: ['밀도'],
  },
] as ExportFormat[]

const CARD = {
  id: 'c1',
  label: '인장 MD (상온)',
  available_formats: ['abaqus'],
} as unknown as PropertyCard

//: 덱 두 줄 — 7번째 칸부터 E, 그 뒤에 ν. 둘째 줄의 G 는 E 와 ν 에서 셈한다.
const LAYOUT: DeckLayout = {
  ok: true,
  format: 'abaqus',
  units: 'si',
  filename: 'SECC_MD_si.inp',
  text: '*ELASTIC\n205000, 0.3\n** G 78846',
  line_count: 3,
  truncated: false,
  values: [
    {
      name: 'elastic.youngs_modulus',
      block: 'elastic',
      key: 'youngs_modulus',
      block_label: '탄성',
      label: '탄성계수',
      column: false,
      unit: 'MPa',
      value: 205000,
      rows: 0,
      spans: [
        { line: 1, start: 0, end: 6, shared_with: [] },
        { line: 2, start: 5, end: 10, shared_with: ['elastic.poisson_ratio'] },
      ],
    },
    {
      name: 'elastic.poisson_ratio',
      block: 'elastic',
      key: 'poisson_ratio',
      block_label: '탄성',
      label: '푸아송비',
      column: false,
      unit: null,
      value: 0.3,
      rows: 0,
      spans: [
        { line: 1, start: 8, end: 11, shared_with: [] },
        { line: 2, start: 5, end: 10, shared_with: ['elastic.youngs_modulus'] },
      ],
    },
  ],
  unused: [
    { name: 'thermal.specific_heat', block_label: '열물성', label: '비열', column: false },
  ],
  failed: [],
  notes: ['밀도가 카드에 없어 *DENSITY 를 뺐습니다.'],
  fail_option: false,
  fail_from_elongation: false,
  error: null,
}

beforeEach(() => {
  download.mockClear()
  layout.mockReset()
  layout.mockResolvedValue(LAYOUT)
  unitSystems.mockReset()
  unitSystems.mockResolvedValue(SYSTEMS)
})

async function open(card: PropertyCard = CARD, formats: ExportFormat[] = FORMATS) {
  render(<ExportMenu card={card} formats={formats} onError={() => {}} />)
  await userEvent.click(screen.getByRole('button', { name: /내보내기/ }))
  const dialog = await screen.findByRole('dialog')
  // 계 목록이 **서버에서 와서 그려진 뒤**를 기다린다 — 틀만 선 화면을 보지 않는다.
  await within(dialog).findByRole('button', { name: /SI \(kg/ })
  return dialog
}

/** 솔버 카드 열 — 형식 단추는 여기서 찾는다. 툴 열에도 같은 이름(「Abaqus」)의 단추가 있다. */
function cards() {
  return within(screen.getByRole('navigation', { name: '솔버 카드' }))
}

/** 툴 열. */
function tools() {
  return within(screen.getByRole('navigation', { name: '툴' }))
}

/** 형식을 고르고, 배치가 그려진 뒤 「내려받기」 를 누른다. */
async function pickAndDownload(name: RegExp) {
  await userEvent.click(cards().getByRole('button', { name }))
  const button = await screen.findByRole('button', { name: /내려받기/ })
  await waitFor(() => expect(button).toBeEnabled())
  await userEvent.click(button)
  await waitFor(() => expect(download).toHaveBeenCalled())
}

describe('단위계를 고른다', () => {
  it('안 고르면 서버가 기본이라 한 것으로 보이고 낸다', async () => {
    // **화면이 `si` 를 적어 두지 않는다.** 기본이 무엇인지는 서버가 안다.
    await open()
    await pickAndDownload(/Abaqus/)
    expect(layout.mock.calls[0][2]).toMatchObject({ key: 'si' })
    const [, , , picked] = download.mock.calls[0] as unknown as unknown[]
    expect(picked).toMatchObject({ key: 'si' })
  })

  it('고른 계가 배치와 내려받기에 함께 실린다', async () => {
    await open()
    await userEvent.click(screen.getByRole('button', { name: /mm · N · tonne/ }))
    await pickAndDownload(/Abaqus/)
    expect(layout.mock.calls.at(-1)?.[2]).toMatchObject({ key: 'mm_n_tonne' })
    const [, , , picked] = download.mock.calls[0] as unknown as unknown[]
    expect(picked).toMatchObject({ key: 'mm_n_tonne' })
  })

  it('계를 바꾸면 그 계로 배치를 다시 묻는다', async () => {
    // 앞 계의 배치가 남아 있으면 「이 칸에 이 값」 이 다른 덱을 가리킨다.
    await open()
    await userEvent.click(cards().getByRole('button', { name: /Abaqus/ }))
    await screen.findByRole('table', { name: '칸 배치' })
    await userEvent.click(screen.getByRole('button', { name: /mm · N · tonne/ }))
    await waitFor(() => expect(layout.mock.calls.at(-1)?.[2]).toMatchObject({ key: 'mm_n_tonne' }))
  })

  it('덱에 적힐 줄을 그대로 보인다', async () => {
    // 받는 사람이 파일에서 읽을 글자와 같아야 나중에 대조할 수 있다.
    await open()
    expect(screen.getByText('kg, m, s, Pa')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /mm · N · tonne/ }))
    expect(screen.getByText('tonne, mm, s, MPa')).toBeInTheDocument()
  })

  it('목록을 서버에서 받는다', async () => {
    await open()
    expect(unitSystems).toHaveBeenCalled()
    for (const system of SYSTEMS) {
      expect(screen.getByRole('button', { name: system.label })).toBeInTheDocument()
    }
  })
})

describe('칸 배치와 미리보기', () => {
  it('값마다 덱에 적히는 값 · 자리 · 함께 셈한 칸이 서고, 덱을 그대로 보인다', async () => {
    await open()
    // 고르기 전에는 묻지 않는다 — 형식마다 덱을 그려야 하는 일이다.
    expect(layout).not.toHaveBeenCalled()
    await userEvent.click(cards().getByRole('button', { name: /Abaqus/ }))

    const table = await screen.findByRole('table', { name: '칸 배치' })
    const row = within(table).getByRole('row', { name: /^탄성 · 탄성계수/ })
    expect(row).toHaveTextContent('205000 MPa')
    // 줄 · 칸은 1 부터 — 덱을 연 편집기의 줄 번호와 같게.
    expect(row).toHaveTextContent('2줄 1–6칸 외 1곳')
    expect(row).toHaveTextContent('함께 셈한 칸: 푸아송비')
    expect(screen.getByText(/이 형식이 안 쓰는 값: 열물성 · 비열/)).toBeInTheDocument()
    expect(screen.getByText('밀도가 카드에 없어 *DENSITY 를 뺐습니다.')).toBeInTheDocument()
    expect(screen.getByText('SECC_MD_si.inp')).toBeInTheDocument()

    const deck = screen.getByLabelText('덱 본문')
    expect(deck).toHaveTextContent('*ELASTIC')
    const marked = deck.querySelectorAll('mark')
    expect([...marked].map((one) => one.textContent)).toEqual(['205000', '0.3', '78846'])
    // 여럿에서 셈한 칸은 그 값들을 함께 말한다.
    expect(marked[2]).toHaveAttribute('title', '탄성 · 탄성계수 · 탄성 · 푸아송비')
  })

  it('줄을 누르면 그 값의 자리를 짙게 칠한다', async () => {
    await open()
    await userEvent.click(cards().getByRole('button', { name: /Abaqus/ }))
    const table = await screen.findByRole('table', { name: '칸 배치' })
    await userEvent.click(within(table).getByRole('row', { name: /^탄성 · 푸아송비/ }))

    const marks = [...screen.getByLabelText('덱 본문').querySelectorAll('mark')]
    const strong = marks.filter((one) => one.className.includes('ring-1'))
    expect(strong.map((one) => one.textContent)).toEqual(['0.3', '78846'])
  })

  it('서버가 못 낸다고 하면 까닭을 말하고 내려받기를 잠근다', async () => {
    layout.mockResolvedValue({
      ok: false,
      format: 'abaqus',
      units: 'si',
      error: 'Abaqus 덱에 푸아송비 가 필요한데 카드에 없습니다.',
    })
    await open()
    await userEvent.click(cards().getByRole('button', { name: /Abaqus/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('푸아송비 가 필요한데')
    expect(screen.getByRole('button', { name: /내려받기/ })).toBeDisabled()
  })
})

describe('파단 칸 켜기 (ADR 0059 후속)', () => {
  it('서버가 고를 수 있다고 할 때만 서고, 켜면 미리보기와 내려받기에 함께 실린다', async () => {
    // 고를 수 있는지는 서버가 켜고 끈 덱을 그려 보고 정한다 — 화면은 형식 이름을 모른다.
    layout.mockImplementation((...args: unknown[]) =>
      Promise.resolve({
        ...LAYOUT,
        fail_option: true,
        fail_from_elongation: args[4] === true,
        text: args[4] === true ? '$ FAIL = ln(1+A) = 0.2231' : '$ FAIL not set',
      })
    )
    await open()
    await userEvent.click(cards().getByRole('button', { name: /Abaqus/ }))
    const box = await screen.findByRole('checkbox', { name: /추정 파단 변형률을 파단 칸에 넣기/ })
    expect(box).not.toBeChecked()

    await userEvent.click(box)
    // 미리보기가 켠 덱으로 다시 선 것을 기다린다 — 그 전에는 받지 않는다.
    await waitFor(() =>
      expect(screen.getByLabelText('덱 본문')).toHaveTextContent('$ FAIL = ln(1+A) = 0.2231')
    )
    expect(layout.mock.calls.at(-1)?.[4]).toBe(true)
    const button = screen.getByRole('button', { name: /내려받기/ })
    await waitFor(() => expect(button).toBeEnabled())
    await userEvent.click(button)
    await waitFor(() => expect(download).toHaveBeenCalled())
    expect(download.mock.calls[0][5]).toBe(true)
  })

  it('고를 수 없는 형식이면 서지 않는다', async () => {
    await open()
    await userEvent.click(cards().getByRole('button', { name: /Abaqus/ }))
    await screen.findByRole('table', { name: '칸 배치' })
    expect(screen.queryByRole('checkbox', { name: /파단 칸/ })).not.toBeInTheDocument()
  })
})

describe('낼 수 없는 형식', () => {
  it('접혀 있다가 펼치면 이유를 말하고, 골라도 받지 않는다', async () => {
    // 내려받기를 누른 뒤에 "밀도가 없습니다" 를 보는 것은 늦다. **없애지 않는다** — 왜 못
    // 내는지가 그 자리에 있다.
    await open()
    // 툴 열에는 늘 선다 — 접히는 것은 솔버 카드 열의 그 형식이다.
    expect(cards().queryByText('OpenRadioss')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /못 내는 형식 1개/ }))
    expect(screen.getByText(/밀도 가 있어야 냅니다/)).toBeInTheDocument()
    await userEvent.click(cards().getByRole('button', { name: /OpenRadioss/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('이 카드로는 못 냅니다')
    expect(screen.queryByRole('button', { name: /내려받기/ })).not.toBeInTheDocument()
    expect(layout).not.toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
  })
})

describe('솔버로 묶는다', () => {
  it('괄호 앞이 같은 형식은 한 제목 아래 선다', async () => {
    const models = [
      { key: 'ansys_elastic', label: 'ANSYS (선형)', extension: 'mac', describe: 'MP', requires: [] },
      { key: 'ansys_plastic', label: 'ANSYS (탄소성)', extension: 'mac', describe: 'TB', requires: [] },
      { key: 'dyna', label: 'LS-DYNA (탄소성)', extension: 'k', describe: '024', requires: [] },
    ] as ExportFormat[]
    const card = {
      ...CARD,
      available_formats: models.map((one) => one.key),
    } as unknown as PropertyCard
    await open(card, models)
    const nav = screen.getByRole('navigation', { name: '솔버 카드' })
    expect(within(nav).getAllByText('ANSYS')).toHaveLength(1)
    expect(within(nav).getByText('LS-DYNA')).toBeInTheDocument()
    await pickAndDownload(/ANSYS \(탄소성\)/)
    expect(download.mock.calls[0][1]).toMatchObject({ key: 'ansys_plastic' })
  })

  it('툴 열에서 툴을 고르면 그 툴의 카드만, 「전체」 면 전부 선다 (2026-10-04)', async () => {
    // 솔버 × 물성 모델로 형식이 쉰 개가 넘는다 — 툴을 먼저 고른다. 못 내는 형식뿐인 툴도 선다.
    const models = [
      { key: 'ansys_elastic', label: 'ANSYS (선형)', extension: 'mac', describe: 'MP', requires: [] },
      { key: 'ansys_plastic', label: 'ANSYS (탄소성)', extension: 'mac', describe: 'TB', requires: [] },
      { key: 'dyna', label: 'LS-DYNA (탄소성)', extension: 'k', describe: '024', requires: [] },
      { key: 'openradioss', label: 'OpenRadioss', extension: 'rad', describe: 'LAW36', requires: ['밀도'] },
    ] as ExportFormat[]
    const card = {
      ...CARD,
      available_formats: ['ansys_elastic', 'ansys_plastic', 'dyna'],
    } as unknown as PropertyCard
    await open(card, models)

    // 「전체」 가 기본이고, 툴마다 낼 수 있는 수 / 전체 수.
    expect(tools().getByRole('button', { name: /전체/ })).toHaveAttribute('aria-pressed', 'true')
    expect(tools().getByRole('button', { name: /전체/ })).toHaveTextContent('3/4')
    expect(tools().getByRole('button', { name: /ANSYS/ })).toHaveTextContent('2/2')
    expect(tools().getByRole('button', { name: /OpenRadioss/ })).toHaveTextContent('0/1')
    expect(cards().getByRole('button', { name: /LS-DYNA \(탄소성\)/ })).toBeInTheDocument()

    await userEvent.click(tools().getByRole('button', { name: /ANSYS/ }))
    expect(cards().getByRole('button', { name: /ANSYS \(선형\)/ })).toBeInTheDocument()
    expect(cards().getByRole('button', { name: /ANSYS \(탄소성\)/ })).toBeInTheDocument()
    expect(cards().queryByRole('button', { name: /LS-DYNA/ })).not.toBeInTheDocument()

    // 못 내는 것뿐인 툴 — 까닭과 함께 접혀 있다.
    await userEvent.click(tools().getByRole('button', { name: /OpenRadioss/ }))
    expect(cards().getByText(/OpenRadioss 에 낼 수 있는 형식이 없습니다/)).toBeInTheDocument()
    await userEvent.click(cards().getByRole('button', { name: /못 내는 형식 1개/ }))
    expect(cards().getByText(/밀도 가 있어야 냅니다/)).toBeInTheDocument()

    await userEvent.click(tools().getByRole('button', { name: /전체/ }))
    expect(cards().getByRole('button', { name: /LS-DYNA \(탄소성\)/ })).toBeInTheDocument()
    expect(cards().getByRole('button', { name: /ANSYS \(선형\)/ })).toBeInTheDocument()
  })
})

describe('짝 카드와 합쳐 낸다', () => {
  it('짝을 고르면 새로 낼 수 있는 형식이 서고, 그 짝을 실어 보고 받는다', async () => {
    // 이방성(r값) 카드는 혼자서는 Hill 형식을 못 낸다 — 경화 곡선·탄성이 MD 카드에 있다.
    const hill = [
      { key: 'dyna_hill', label: 'LS-DYNA (이방성 Hill48 · 쉘)', extension: 'k', describe: '036', requires: ['탄성계수'] },
    ] as ExportFormat[]
    const aniso = {
      id: 'a1',
      material_id: 'm1',
      label: '이방성 r',
      orientation: null,
      available_formats: [],
    } as unknown as PropertyCard
    const md = {
      id: 'c-md',
      material_id: 'm1',
      label: '인장 MD',
      orientation: 'MD',
      available_formats: [],
    } as unknown as PropertyCard
    const other = { ...md, id: 'c-x', material_id: 'm2', label: '다른 재료' } as PropertyCard
    pairedFormats.mockResolvedValue({ available_formats: ['dyna_hill'], borrowed_blocks: ['table'] })
    render(<ExportMenu card={aniso} formats={hill} onError={() => {}} siblings={[aniso, md, other]} />)
    await userEvent.click(screen.getByRole('button', { name: /내보내기/ }))
    // 같은 재료의 다른 카드만 짝 후보다 — 자기 자신과 다른 재료는 안 선다.
    expect(await screen.findByRole('button', { name: /인장 MD · MD/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /다른 재료/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /인장 MD · MD/ }))
    expect(pairedFormats).toHaveBeenCalledWith('a1', 'c-md')

    const nav = screen.getByRole('navigation', { name: '솔버 카드' })
    await userEvent.click(await within(nav).findByRole('button', { name: /LS-DYNA \(이방성/ }))
    await waitFor(() => expect(layout).toHaveBeenCalled())
    expect(layout.mock.calls[0][3]).toBe('c-md')
    const button = await screen.findByRole('button', { name: /내려받기/ })
    await waitFor(() => expect(button).toBeEnabled())
    await userEvent.click(button)
    await waitFor(() => expect(download).toHaveBeenCalled())
    const call = download.mock.calls[0] as unknown as unknown[]
    expect(call[4]).toBe('c-md')
  })
})

describe('단위가 정해진 형식', () => {
  it('고른 계와 상관없이 그 계로 나간다고 형식 줄에 말한다', async () => {
    // AEDT · CST · Zemax 는 파일 형식이 단위를 정해 두었다 — 위에서 mm·N·tonne 을 골랐는데
    // SI 파일이 오면 사람은 서버가 틀렸다고 읽는다. **고르기 전에** 그 사실이 보여야 한다.
    const formats = [
      {
        key: 'aedt',
        label: 'Ansys Electronics Desktop (전자기 재료)',
        extension: 'amat',
        describe: 'HFSS · Maxwell 재료 라이브러리',
        requires: [],
        fixed_units: 'si',
      },
      ...FORMATS,
    ] as ExportFormat[]
    const card = { ...CARD, available_formats: ['aedt', 'abaqus'] } as unknown as PropertyCard
    await open(card, formats)

    const aedt = cards().getByRole('button', { name: /Ansys Electronics Desktop/ })
    expect(aedt).toHaveTextContent('고른 계와 상관없이 SI로 나갑니다')
    const abaqus = cards().getByRole('button', { name: /Abaqus/ })
    expect(abaqus).not.toHaveTextContent('고른 계와 상관없이')
  })
})
