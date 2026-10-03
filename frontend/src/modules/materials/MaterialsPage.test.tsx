/**
 * 재료 목록의 **일괄 삭제** — 무엇을 지우겠다고 서버에 말하는가.
 *
 * 여기서 틀리면 사라지는 것이 고른 재료가 아니라 그 아래 트리 전체다. 그리고
 * 사람이 「예」 를 누른 근거는 이 화면이 보여 준 숫자이므로, 숫자와 실제가
 * 어긋나면 그 「예」 는 다른 것에 대한 대답이 된다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LENGTH_UNIT } from '@/modules/materials/api'
import MaterialsPage from '@/modules/materials/MaterialsPage'

const list = vi.fn()
const classifications = vi.fn()
const bulkDeletePlan = vi.fn()
const removeMany = vi.fn()
const workspaces = vi.fn()

const download = vi.fn()
const testTypes = vi.fn()

// 상세 조건의 「이 시험이 있는 재료」 선택지. 상세 조건을 열 때만 부른다.
vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: { types: () => testTypes() },
}))

vi.mock('@/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/client')>()),
  downloadFile: (...args: unknown[]) => download(...args),
}))

// 계 목록은 서버가 준다(ADR 0036). **기본이 첫째가 아니다** — 순서로 고르면 통과해 버린다.
vi.mock('@/shared/api/unitSystems', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/unitSystems')>()),
  unitSystemsApi: {
    list: () =>
      Promise.resolve([
        { key: 'si', label: 'SI (kg · m · s · Pa)', is_default: false },
        { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)', is_default: true },
      ]),
  },
}))

// 계 목록은 서버가 준다(ADR 0036). **기본이 첫째가 아니다** — 순서로 고르면 통과해 버린다.
vi.mock('@/shared/api/unitSystems', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/unitSystems')>()),
  unitSystemsApi: {
    list: () =>
      Promise.resolve([
        { key: 'si', label: 'SI (kg · m · s · Pa)', is_default: false },
        { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)', is_default: true },
      ]),
  },
}))

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    list: (...args: unknown[]) => list(...args),
    classifications: () => classifications(),
    bulkDeletePlan: (...args: unknown[]) => bulkDeletePlan(...args),
    removeMany: (...args: unknown[]) => removeMany(...args),
    workspaces: () => workspaces(),
  },
}))

const VIEWER = { user: { is_system_admin: true, memberships: [] } }

// 목록에 「담기」 패널이 얹혀 있고 그것이 부서를 묻는다(`useMaybeAuth`) —
// 곁들이 위젯이라 제공자가 없어도 서지만, 모듈을 통째로 대신할 때는 같이 준다.
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => VIEWER,
  useMaybeAuth: () => VIEWER,
}))

function material(id: string, name: string) {
  return {
    id,
    record_name: name,
    alias: null,
    family: 'Metal',
    category: 'Steel',
    grade: name,
    details: null,
    // API 는 SI 다(2026-09-24) — 화면이 mm 로 바꿔 보인다.
    spec_thickness: 0.001,
    spec_thickness_unit: 'm',
    owner_workspace_id: null,
    owner_workspace_name: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function plan(samples: number, specimens: number, test_runs: number, blocked = []) {
  return { materials: 2, samples, specimens, test_runs, blocked }
}

beforeEach(() => {
  list.mockReset()
  download.mockReset()
  testTypes.mockResolvedValue([{ key: 'tensile', label: '인장시험' }])
  classifications.mockReset()
  bulkDeletePlan.mockReset()
  workspaces.mockResolvedValue([{ id: 'w1', slug: 'metal', name: '금속재료팀' }])
  removeMany.mockReset()
  list.mockResolvedValue({
    items: [material('m1', 'SPCC_-_1.2'), material('m2', 'SGCC_-_0.8')],
    total: 2,
    limit: 50,
    offset: 0,
  })
  classifications.mockResolvedValue([])
  removeMany.mockResolvedValue({ deleted: 2, blocked: [], samples: 0, specimens: 0, test_runs: 0 })
})

function show() {
  return render(
    <MemoryRouter>
      <MaterialsPage />
    </MemoryRouter>
  )
}

/** 두 재료를 고르고 「지우기」 를 눌러 확인창을 연다. */
async function pickAndOpen(user: ReturnType<typeof userEvent.setup>) {
  // **이름은 조각으로 그려진다.** `RecordName` 이 값이 없는 칸(`-`)만 흐리게
  // 그리느라 span 을 나눈다 — 글자는 그대로지만 `findByText` 의 기본 대조는
  // 직계 텍스트만 보므로 안 걸린다. 링크의 이름으로 찾으면 조각이 합쳐진다.
  await screen.findByRole('link', { name: 'SPCC_-_1.2' })
  const boxes = screen.getAllByRole('checkbox')
  // 첫 칸은 '전부 고르기' 다. 그것을 눌러 둘을 함께 고른다.
  await user.click(boxes[0])
  await user.click(await screen.findByRole('button', { name: /삭제/ }))
}

describe('일괄 삭제', () => {
  it('열 때 무엇이 딸려 있는지 서버에 묻는다', async () => {
    // **화면이 세지 않는다.** 목록에는 시료·시편 수가 없고, 있다 해도 화면이
    // 나름대로 세면 실제로 지워지는 것과 어긋난다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)

    await waitFor(() => expect(bulkDeletePlan).toHaveBeenCalledWith(['m1', 'm2']))
    expect(await screen.findByText(/시료 2건 · 시편 6건/)).toBeInTheDocument()
  })

  it('기본은 아래를 안 지운다', async () => {
    // **고르고 지우기를 누르는 것이 갑자기 트리를 날리는 뜻이 되면 안 된다.**
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시료 2건/)

    await user.click(screen.getByRole('button', { name: '삭제', hidden: false }))
    await waitFor(() =>
      expect(removeMany).toHaveBeenCalledWith(['m1', 'm2'], {
        cascade: false,
        includeTestRuns: false,
      })
    )
  })

  it('켜면 아래까지 지운다고 말한다', async () => {
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시료 2건/)

    await user.click(screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ }))
    await user.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() =>
      expect(removeMany).toHaveBeenCalledWith(['m1', 'm2'], {
        cascade: true,
        includeTestRuns: false,
      })
    )
  })

  it('시험 칸은 아래까지를 켜야 뜬다', async () => {
    // 늘 띄우면 사람이 습관적으로 켜게 되고, 그러면 칸이 막는 일을 못 한다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 4))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시험 4건/)

    expect(screen.queryByRole('checkbox', { name: /시험 4건도 함께/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ }))
    expect(await screen.findByRole('checkbox', { name: /시험 4건도 함께/ })).toBeInTheDocument()
  })

  it('아래까지를 끄면 시험 칸도 함께 꺼진다', async () => {
    // **켠 채로 숨으면 그 뜻이 그대로 서버에 간다.** 사람은 껐다고 생각한다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 4))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시험 4건/)

    const cascade = screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ })
    await user.click(cascade)
    await user.click(await screen.findByRole('checkbox', { name: /시험 4건도 함께/ }))
    await user.click(cascade)
    await user.click(cascade)

    await user.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() =>
      expect(removeMany).toHaveBeenCalledWith(['m1', 'm2'], {
        cascade: true,
        includeTestRuns: false,
      })
    )
  })

  it('딸려 간 것을 지운 뒤에 말한다', async () => {
    // "2건 지웠습니다" 만 뜨면 사람은 시편 여섯이 함께 사라진 것을 모른다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    removeMany.mockResolvedValue({
      deleted: 2,
      blocked: [],
      samples: 2,
      specimens: 6,
      test_runs: 0,
    })
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시료 2건/)
    await user.click(screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ }))
    await user.click(screen.getByRole('button', { name: '삭제' }))

    expect(
      await screen.findByText(/재료 2건과 함께 시료 2건 · 시편 6건을 지웠습니다/)
    ).toBeInTheDocument()
  })
  it('지금 거른 조건 그대로, 고른 단위계로 내보낸다', async () => {
    // **「화면에서 본 것」 과 「받아 간 파일」 이 달라지면 안 된다** — 받아 간
    // 쪽이 틀렸다는 것을 알아챌 방법이 없다. 계는 고르지 않으면 서버 기본이고, 파일
    // 이름이 그 계를 말한다(ADR 0036).
    const user = userEvent.setup()
    show()
    await screen.findByRole('link', { name: 'SPCC_-_1.2' })

    await user.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
    await user.click(
      await screen.findByRole('menuitem', { name: /matnexus_materials_mm_n_tonne\.json/ })
    )
    await waitFor(() => expect(download).toHaveBeenCalled())
    const [url, filename] = download.mock.calls[0] as [string, string]
    const sent = new URL(url, 'http://localhost')
    expect(sent.pathname).toBe('/materials/export')
    expect(sent.searchParams.get('units')).toBe('mm_n_tonne')
    expect(filename).toBe('matnexus_materials_mm_n_tonne.json')
  })

  it('내보내기가 실패하면 그렇다고 말한다', async () => {
    // **안 잡으면 422 · 500 이 나도 화면에 아무것도 안 뜬다**(2026-10-04).
    download.mockRejectedValueOnce(new Error('너무 많아 한 번에 못 담습니다'))
    const user = userEvent.setup()
    show()
    await screen.findByRole('link', { name: 'SPCC_-_1.2' })

    await user.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
    await user.click(
      await screen.findByRole('menuitem', { name: /matnexus_materials_mm_n_tonne\.json/ })
    )
    expect(await screen.findByText('너무 많아 한 번에 못 담습니다')).toBeInTheDocument()
  })
})

describe('찾기 — 방식과 상세 조건 (2026-09-29)', () => {
  /** 마지막으로 서버에 보낸 질의. */
  function lastQuery(): Record<string, unknown> {
    return (list.mock.calls.at(-1)?.[0] ?? {}) as Record<string, unknown>
  }

  it('「비슷」 은 곧바로 그 방식으로 묻고, 줄마다 왜 걸렸는지 선다', async () => {
    list.mockResolvedValue({
      items: [
        { ...material('m1', 'SPCC_-_1.2'), matched: 'meaning' },
        { ...material('m2', 'SGCC_-_0.8'), matched: 'similar' },
      ],
      total: 2,
      limit: 50,
      offset: 0,
    })
    const user = userEvent.setup()
    show()
    await screen.findByRole('link', { name: 'SPCC_-_1.2' })

    await user.type(screen.getByRole('textbox', { name: '재료 찾기' }), '아연도금 강판')
    await user.click(screen.getByRole('button', { name: '찾기' }))
    await waitFor(() => expect(lastQuery().q).toBe('아연도금 강판'))
    // 「포함」 은 서버 기본값이라 안 보낸다.
    expect(lastQuery().mode).toBeUndefined()

    const modes = screen.getByRole('group', { name: '찾는 방식' })
    await user.click(within(modes).getByRole('button', { name: '비슷' }))
    await waitFor(() => expect(lastQuery().mode).toBe('similar'))
    expect(lastQuery().q).toBe('아연도금 강판')

    // **왜 걸렸는지** — 뜻으로만 걸린 줄에 이유가 없으면 엉뚱한 결과로 읽힌다.
    expect(await screen.findByText('뜻이 가까움')).toBeInTheDocument()
    expect(screen.getByText('비슷함')).toBeInTheDocument()
  })

  it('상세 조건은 찾기를 누를 때 걸리고, 두께는 화면 단위를 함께 싣는다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByRole('link', { name: 'SPCC_-_1.2' })

    await user.click(screen.getByRole('button', { name: /상세 조건/ }))
    await user.type(screen.getByRole('textbox', { name: '용도(적용 제품·부위)' }), '범퍼')
    await user.type(screen.getByRole('spinbutton', { name: '두께 하한' }), '1')
    await user.type(screen.getByRole('spinbutton', { name: '두께 상한' }), '1.2')
    // 선택지는 서버가 준다 — 그려진 뒤에 고른다.
    await screen.findByRole('option', { name: '인장시험' })
    await user.selectOptions(
      screen.getByRole('combobox', { name: '이 시험이 있는 재료' }),
      'tensile'
    )

    // 적기만 해서는 안 걸린다 — 한 글자마다 목록을 다시 부르지 않는다.
    expect(list.mock.calls.some(([query]) => (query as Record<string, unknown>).use)).toBe(
      false
    )

    await user.click(screen.getByRole('button', { name: '이 조건으로 찾기' }))
    await waitFor(() => expect(lastQuery().use).toBe('범퍼'))
    // **단위 없이 1.2 를 보내면 서버는 1.2 m 로 읽는다.**
    expect(lastQuery()).toMatchObject({
      thickness_min: 1,
      thickness_max: 1.2,
      thickness_unit: LENGTH_UNIT,
      test_type: 'tensile',
    })
    expect(screen.getByRole('button', { name: /상세 조건 · 3/ })).toBeInTheDocument()

    // 초기화는 곧바로 푼다.
    await user.click(screen.getByRole('button', { name: '초기화' }))
    await waitFor(() => expect(lastQuery().use).toBeUndefined())
    expect(lastQuery().thickness_unit).toBeUndefined()
  })

  it('내보내기에 방식과 상세 조건이 그대로 실린다 — 정렬은 빼고', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByRole('link', { name: 'SPCC_-_1.2' })

    await user.type(screen.getByRole('textbox', { name: '재료 찾기' }), 'SECC')
    const modes = screen.getByRole('group', { name: '찾는 방식' })
    await user.click(within(modes).getByRole('button', { name: '비슷' }))
    await user.click(screen.getByRole('button', { name: /상세 조건/ }))
    await user.type(screen.getByRole('textbox', { name: '제조사·거래처' }), '포스코')
    await user.click(screen.getByRole('button', { name: '찾기' }))
    await waitFor(() => expect(lastQuery().maker).toBe('포스코'))

    await user.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
    await user.click(
      await screen.findByRole('menuitem', { name: /matnexus_materials_mm_n_tonne\.json/ })
    )
    await waitFor(() => expect(download).toHaveBeenCalled())
    const [url] = download.mock.calls.at(-1) as [string, string]
    const sent = new URL(url, 'http://localhost')
    expect(sent.searchParams.get('q')).toBe('SECC')
    expect(sent.searchParams.get('mode')).toBe('similar')
    expect(sent.searchParams.get('maker')).toBe('포스코')
    expect(sent.searchParams.get('sort')).toBeNull()
  })
})
