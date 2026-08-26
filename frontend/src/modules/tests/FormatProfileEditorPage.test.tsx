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

    expect(await screen.findByText(/만들다 만 것이 이 브라우저에 남아 있습니다/)).toBeInTheDocument()
    // 아직 안 채웠다 — 사람이 누르기 전까지는 저장된 것이 보여야 한다.
    expect(screen.getByDisplayValue('옛 앱 인장 결과')).toBeInTheDocument()

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
