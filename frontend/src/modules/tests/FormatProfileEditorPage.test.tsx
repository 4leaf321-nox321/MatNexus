/**
 * 형식 프로파일 편집기 — **여기에 시험이 하나도 없었다.**
 *
 * 1600줄짜리 화면인데 시험이 없어서, 저장된 프로파일을 열고 **아무것도 안
 * 고치고 저장만 눌러도** 단위와 `skip` 이 사라지는 것을 아무도 못 잡았다.
 * 그 왕복이 이 파일의 첫 시험이다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import FormatProfileEditorPage from '@/modules/tests/FormatProfileEditorPage'

const updateFormat = vi.fn((..._args: unknown[]) => Promise.resolve({}))
const previewFormat = vi.fn()

/** `legacy_mtet` 이 실제로 갖고 있는 모양 — 단위와 `skip` 이 함께 든다. */
const SAVED = {
  id: 'p1',
  key: 'legacy_mtet',
  label: '옛 앱 인장 결과',
  description: null,
  test_type_key: 'tensile',
  priority: 10,
  is_active: true,
  is_global: true,
  owner_workspace_slug: null,
  owner_workspace_name: null,
  definition: {
    match: { extensions: ['.mtet'], header_any: ['Standard extensometer (mm)'] },
    tables: { mode: 'first' },
    columns: {
      '#': { skip: true },
      'Standard extensometer (mm)': { channel: 'displacement', unit: 'mm' },
      'Standard load cell (N)': { channel: 'force', unit: 'N' },
    },
    summary: { 'Force maximum (MPa)': { key: 'legacy_tensile_strength', unit: 'MPa' } },
    specimen: {
      'Specimen thickness a0 (mm)': { key: 'specimen_thickness', unit: 'mm' },
    },
    // **이관 전용 자리.** 올릴 때는 안 쓰지만 정의에는 산다 — 열고 저장만
    // 눌러도 사라지면, 그 사실을 이관 당일에야 알게 된다.
    material: {
      'Spec thickness (mm)': { field: 'spec_thickness', unit: 'mm' },
      'Material family': { field: 'family' },
    },
    sample: {
      Maker: { field: 'manufacturer' },
      'Made on': { field: 'production_date', format: '%Y/%m/%d' },
    },
    metadata: ['Operator'],
  },
}

const TYPE = {
  id: 't1',
  key: 'tensile',
  label: '인장시험',
  abbr: 'TEN',
  description: null,
  parser_key: null,
  extensions: [],
  is_active: true,
  max_upload_bytes: null,
  revision: 3,
  owner_workspace_slug: null,
  owner_workspace_name: null,
  is_global: true,
  sort_order: 0,
  channels: [
    {
      key: 'displacement',
      label: '변위',
      dimension: 'length',
      si_unit: 'm',
      is_required: true,
      sort_order: 0,
    },
    {
      key: 'force',
      label: '하중',
      dimension: 'force',
      si_unit: 'N',
      is_required: true,
      sort_order: 10,
    },
  ],
  conditions: [],
}

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: () => Promise.resolve([TYPE]),
    formats: () => Promise.resolve([SAVED]),
    updateFormat: (...args: unknown[]) => updateFormat(...args),
    previewFormat: (...args: unknown[]) => previewFormat(...args),
    tryFormat: () => Promise.resolve({ curves: [], summary: [], metadata: {}, warnings: [] }),
  },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

function open(key = 'legacy_mtet') {
  return render(
    <MemoryRouter initialEntries={[`/settings/formats/${key}`]}>
      <Routes>
        <Route path="/settings/formats/:key" element={<FormatProfileEditorPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  updateFormat.mockClear()
  previewFormat.mockReset()
  window.localStorage.clear()
})

describe('저장된 프로파일을 열었을 때', () => {
  it('아무것도 안 고치고 저장하면 정의가 그대로다', async () => {
    // **이것이 이 파일이 존재하는 이유다.** 전에는 불러오기가 `channel` 하나만
    // 읽어서, 열고 저장만 눌러도 `unit` 과 `skip` 이 사라졌다. 그러면 그
    // 순간부터 모든 `.mtet` 등록이 실패한다 — 그 파일은 단위 줄이 없다.
    open()
    await screen.findByDisplayValue('옛 앱 인장 결과')

    await userEvent.click(await screen.findByRole('button', { name: /저장/ }))
    await waitFor(() => expect(updateFormat).toHaveBeenCalled())

    const call = updateFormat.mock.calls[0] as unknown as [string, { definition: object }]
    const payload = call[1]
    const sent = payload.definition as typeof SAVED.definition
    expect(sent.columns).toEqual(SAVED.definition.columns)
    expect(sent.summary).toEqual(SAVED.definition.summary)
    expect(sent.specimen).toEqual(SAVED.definition.specimen)
    // **단위와 날짜 형식까지 그대로다.** 열 매핑이 정확히 이 자리에서 무너졌다 —
    // 불러오기가 `field` 만 읽으면 `unit` 과 `format` 이 조용히 사라진다.
    expect(sent.material).toEqual(SAVED.definition.material)
    expect(sent.sample).toEqual(SAVED.definition.sample)
  })

  it('파일을 안 놓아도 저장된 헤더 지문이 보인다', async () => {
    // 전에는 헤더 칸이 **칩 전용**이라, 파일이 없으면 저장된 지문이 화면에서
    // 사라졌다. 그 상태로 저장하면 지문이 날아간다.
    open()
    expect(await screen.findByDisplayValue('Standard extensometer (mm)')).toBeInTheDocument()
  })
})

describe('메타 기본값', () => {
  it('손대지 않은 줄도 「그대로 보관」으로 저장된다', async () => {
    // **화면이 거짓말을 하고 있었다.** 손대지 않은 줄을 「그대로 보관」이라고
    // 그려 놓고, 저장은 손댄 줄만 순회해서 정의에 안 담았다 — 읽는 쪽은 그것을
    // 「하나도 안 남기기로 정했음」 으로 읽는다. 즉 보관이라 하고 전부 버렸다.
    previewFormat.mockResolvedValue({
      filename: 'a.tra',
      encoding: 'utf-8',
      delimiter: ',',
      line_count: 20,
      meta: [
        ['Instrument name', 'Zwick Z100'],
        ['Operator', '홍길동'],
      ],
      tables: [],
      warnings: [],
      matched_profile: null,
    })
    const { container } = open()
    await screen.findByDisplayValue('옛 앱 인장 결과')

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, new File(['x'], 'a.tra', { type: 'text/plain' }))
    await waitFor(() => expect(previewFormat).toHaveBeenCalled())
    // 메타 지문 칩과 ⑤ 의 줄에 같은 글자가 있다 — 여럿이어도 된다.
    await waitFor(() => expect(screen.getAllByText('Instrument name').length).toBeGreaterThan(0))

    // 파일을 놓았으면 **적용해 봐야** 저장이 열린다 — 자동 감지는 틀린다.
    await userEvent.click(screen.getByRole('button', { name: /이 파일에 적용해 보기/ }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^저장$/ })).not.toBeDisabled()
    )
    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }))
    await waitFor(() => expect(updateFormat).toHaveBeenCalled())
    const call = updateFormat.mock.calls[0] as unknown as [string, { definition: object }]
    const sent = call[1].definition as { metadata?: string[] }
    expect(sent.metadata).toEqual(expect.arrayContaining(['Instrument name', 'Operator']))
  })
})

describe('메타 역할 고르기', () => {
  it('갈 곳을 안 정하면 저장을 막는다', async () => {
    // **고르고 나서 아무 일도 안 일어나는 것**이 이 화면에서 제일 헷갈리는
    // 자리였다. `definition()` 은 대상이 있을 때만 담고, 안 담기면 보관
    // 목록에도 안 들어가므로 그 값은 **조용히 사라진다.**
    open()
    await screen.findByDisplayValue('옛 앱 인장 결과')
    expect(screen.getByRole('button', { name: /^저장$/ })).not.toBeDisabled()

    // 「Operator」 는 저장본에서 그대로 보관이다. 결과값으로 바꾸되 키는 안 적는다.
    const roles = screen.getAllByRole('combobox')
    const meta = roles[roles.length - 1]
    await userEvent.click(meta)
    // Radix 는 접근성용 숨은 항목을 함께 그린다. 실제 항목은 `option` 역할을
    // 가진 쪽이고, 숨은 쪽은 `pointer-events: none` 이라 누를 수 없다.
    await userEvent.click(await screen.findByRole('option', { name: /시험 결과값/ }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^저장$/ })).toBeDisabled()
    )
    expect(screen.getByText(/갈 곳을 정하세요/)).toBeInTheDocument()
  })

  it('어디로 가는지 목록에 적어 둔다', async () => {
    // 이름만으로는 결과값·기록·조건이 뭉쳐 읽힌다 — 셋 다 시험에 붙지만
    // 자리가 다르다.
    open()
    await screen.findByDisplayValue('옛 앱 인장 결과')
    const roles = screen.getAllByRole('combobox')
    await userEvent.click(roles[roles.length - 1])

    expect((await screen.findAllByText('시험에 남긴다')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('저장하지 않는다').length).toBeGreaterThan(0)
    for (const said of [
      /우리가 계산한 값과 나란히 비교됩니다/,
      /시험 종류가 선언한 조건 칸/,
      /아무 데도 저장하지 않습니다/,
    ]) {
      expect(screen.getAllByText(said).length).toBeGreaterThan(0)
    }
  })
})

describe('지문 구역', () => {
  it('메타 키 칸의 이름이 「메타 키 지정」 이다', async () => {
    open()
    expect(await screen.findByText('메타 키 지정')).toBeInTheDocument()
    expect(screen.queryByText('메타 키가 있으면')).not.toBeInTheDocument()
  })

  it('칸끼리와 한 칸 안의 규칙이 다르다는 것을 적어 둔다', async () => {
    // 라벨이 명사가 되면서 조건이 라벨에서 빠졌다. 그 규칙을 말할 자리는
    // 여기뿐이다 — 없으면 「지정」 이 AND 로 읽힌다.
    open()
    expect(await screen.findByText(/적은 칸끼리는 모두 맞아야/)).toBeInTheDocument()
    expect(screen.getByText(/한 칸에 여럿 적으면 그중 하나만/)).toBeInTheDocument()
  })
})

describe('단위', () => {
  it('채널 옆에 저장 단위와 화면 단위를 함께 적는다', async () => {
    // **저장 단위만 보이면 「거리의 기본 단위가 m」 으로 읽힌다.** 그리고 바로
    // 옆 「단위 지정」 칸에 그 m 을 적게 되는데, mm 로 적힌 파일이 그러면
    // 1000배로 읽히고 숫자는 그럴듯하다.
    open()
    await screen.findByDisplayValue('옛 앱 인장 결과')
    await userEvent.click(screen.getAllByRole('combobox')[0])
    // 여러 열이 같은 채널을 가리킬 수 있어 여러 번 나온다.
    expect((await screen.findAllByText('저장 m · 화면 mm')).length).toBeGreaterThan(0)
    expect(screen.queryByText('displacement · m')).not.toBeInTheDocument()
  })

  it('단위 지정 칸이 무엇을 받는지 화면이 말한다', async () => {
    open()
    expect(
      await screen.findByText(/단위 지정 칸에는 「파일에 적힌 단위」를 적습니다/)
    ).toBeInTheDocument()
  })
})

describe('표 선택', () => {
  it('측정과 처리결과의 뜻이 항상 보인다', async () => {
    // 전에는 규칙이 안 맞아 건너뛴 표가 있을 때만 설명이 떴다 — 규칙을 다
    // 맞추면 설명이 사라졌다.
    open()
    expect(await screen.findByText('실제로 재서')).toBeInTheDocument()
    expect(screen.getByText('이미 계산해 낸')).toBeInTheDocument()
    expect(screen.getByText(/보관은 하되 처리의 입력으로는 쓰지 않습니다/)).toBeInTheDocument()
  })
})

describe('임시 저장', () => {
  it('고치면 이 브라우저에 적어 둔다', async () => {
    open()
    const label = await screen.findByDisplayValue('옛 앱 인장 결과')
    await userEvent.type(label, '!')

    await waitFor(() => {
      const raw = window.localStorage.getItem('matnexus.profile-draft.legacy_mtet')
      expect(raw).toBeTruthy()
      expect(JSON.parse(raw as string).state.form.label).toContain('!')
    })
  })

  it('남아 있으면 말해 주고, 말없이 채우지 않는다', async () => {
    window.localStorage.setItem(
      'matnexus.profile-draft.legacy_mtet',
      JSON.stringify({
        version: 1,
        at: new Date().toISOString(),
        fileName: 'Test1.mtet',
        state: { form: { ...SAVED, label: '되살린 이름', description: '' } },
      })
    )
    open()

    // **불러오기가 끝나기를 먼저 기다린다.** 배너는 localStorage 라 바로 뜨고
    // 이름은 API 라 나중에 온다 — 배너를 기준으로 삼으면 느린 기계에서 폼이
    // 아직 빈 채로 다음 줄을 읽는다. CI 에서 그렇게 걸렸다(v1.116.0). 목을
    // 400ms 늦추면 이 자리에서 그대로 재현된다.
    expect(await screen.findByDisplayValue('옛 앱 인장 결과')).toBeInTheDocument()
    // 그러고도 배너는 떠 있고 **말없이 채우지는 않았다** — 이것이 요점이다.
    expect(screen.getByText(/만들다 만 것이 이 브라우저에 남아 있습니다/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '이어서 하기' }))
    expect(await screen.findByDisplayValue('되살린 이름')).toBeInTheDocument()
  })

  it('버리면 사라진다', async () => {
    window.localStorage.setItem(
      'matnexus.profile-draft.legacy_mtet',
      JSON.stringify({ version: 1, at: new Date().toISOString(), fileName: null, state: {} })
    )
    open()
    await userEvent.click(await screen.findByRole('button', { name: '버리기' }))
    expect(
      screen.queryByText(/만들다 만 것이 이 브라우저에 남아 있습니다/)
    ).not.toBeInTheDocument()
  })
})
