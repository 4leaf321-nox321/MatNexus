/**
 * 워크벤치 — **고르고, 담고, 어디까지 왔는지 안다**(ADR 0024·0025).
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   무엇을 할지 먼저 고른다      워크플로 목록이 곧 「무엇을 할 수 있나」 다
 *   남은 일을 이름으로 말한다     세기만 하면 어느 것인지 찾으러 다녀야 한다
 *   할 자리로 데려간다           「그 목록 화면에 있습니다」 만 적으면 사람이 찾아야 한다
 *   이어서 하기가 먼저 보인다     어제 것이 아래에 묻히면 서버에 둔 뜻이 없다
 *   사라진 것도 줄을 지킨다       조용히 빠지면 「여덟이 왜 일곱이지」 가 된다
 *   모르는 워크플로는 밀지 않는다  반쯤 읽어 이어서 미는 것이 더 나쁘다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkbenchPage from '@/modules/workbench/WorkbenchPage'

const runs = vi.fn()
const run = vi.fn()
const create = vi.fn()
const patch = vi.fn()
const remove = vi.fn()

vi.mock('@/shared/api/basket', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/basket')>()),
  basketApi: {
    runs: (...args: unknown[]) => runs(...args),
    run: (...args: unknown[]) => run(...args),
    create: (...args: unknown[]) => create(...args),
    patch: (...args: unknown[]) => patch(...args),
    remove: (...args: unknown[]) => remove(...args),
  },
}))

const DETAIL = {
  id: 'r1',
  workspace_id: 'w1',
  owner_id: 'u1',
  owner_name: '박용진',
  workflow_key: 'analysis_deck',
  title: 'EPDM 도어씰 2026-09',
  status: 'running',
  steps: {},
  note: null,
  item_count: 0,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  finished_at: null,
  items: [],
}

function show(at = '/w/metal/workbench') {
  render(
    <MemoryRouter initialEntries={[at]}>
      <WorkbenchPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  runs.mockResolvedValue([])
  run.mockResolvedValue(DETAIL)
  create.mockResolvedValue(DETAIL)
  patch.mockResolvedValue(DETAIL)
  remove.mockResolvedValue(undefined)
})

describe('무엇을 할지 고른다', () => {
  it('워크플로 목록과 단계 수를 미리 보여 준다', async () => {
    // **시작하고 나서 알면 되돌리는 값이 든다.**
    show()
    expect(await screen.findByText('해석에 쓸 물성 갖추기')).toBeInTheDocument()
    expect(screen.getByText('DMA 한 벌로 점탄성 계수 내기')).toBeInTheDocument()
    expect(screen.getByText(/1\. 무엇에 쓰나/)).toBeInTheDocument()
  })

  it('이름을 적어 시작하면 그 워크플로로 만든다', async () => {
    show()
    const name = await screen.findByLabelText('해석에 쓸 물성 갖추기 작업 이름')
    await userEvent.type(name, 'EPDM 도어씰')
    await userEvent.click(within(name.closest('div')!.parentElement!).getByRole('button', { name: /시작/ }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({
      workflow_key: 'analysis_deck',
      title: 'EPDM 도어씰',
    })
  })

  it('이름을 비워도 시작은 된다', async () => {
    // **막지 않는다.** 이름이 없으면 워크플로 이름과 날짜로 짓는다 — 「작업 3」
    // 같은 것보다 낫고, 나중에 고칠 수 있다.
    show()
    const cards = await screen.findAllByRole('button', { name: /시작/ })
    await userEvent.click(cards[0])
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].title).toBeTruthy()
  })
})

describe('이어서 하기', () => {
  it('진행 중인 작업이 목록 위에 뜬다', async () => {
    // 어제 하던 것이 아래에 묻히면 서버에 둔 뜻이 없다.
    runs.mockResolvedValue([{ ...DETAIL, item_count: 3 }])
    show()
    expect(await screen.findByText('이어서 하기')).toBeInTheDocument()
    expect(screen.getByText('EPDM 도어씰 2026-09')).toBeInTheDocument()
    expect(screen.getByText(/담은 것 3/)).toBeInTheDocument()
  })

  it('누르면 그 작업을 연다', async () => {
    runs.mockResolvedValue([DETAIL])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    await waitFor(() => expect(run).toHaveBeenCalledWith('r1'))
    expect(await screen.findByLabelText('바구니')).toBeInTheDocument()
  })
})

function run말고(over: Record<string, unknown>) {
  const sweep = (label: string, curves: number) => ({
    id: label,
    kind: 'test_run',
    target_id: label,
    label,
    detail: 'parsed',
    facts: { master_curves: curves, temperature_steps: 5 },
    material_id: 'm1',
    missing: false,
    note: null,
    added_at: '2026-09-01T00:00:00Z',
  })
  return {
    ...DETAIL,
    workflow_key: 'viscoelastic_set',
    item_count: 2,
    items: [sweep('시편 A', 1), sweep('시편 B', 0)],
    ...over,
  }
}

describe('남은 일을 말한다', () => {
  const openAt = async (detail: Record<string, unknown>) => {
    run.mockResolvedValue(detail)
    runs.mockResolvedValue([detail])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    await screen.findByLabelText('단계')
  }

  it('안 겹친 시험의 이름을 댄다', async () => {
    // 「1건 남음」 만 적으면 사람은 그 한 건을 찾으러 목록을 뒤져야 한다.
    await openAt(run말고({ steps: { at: 'master', done: ['pick'] } }))
    const status = within(await screen.findByLabelText('이 단계 상태'))
    expect(status.getByText(/1건이 아직 안 겹쳤습니다/)).toBeInTheDocument()
    expect(status.getByText('시편 B')).toBeInTheDocument()
  })

  it('다 갖추면 됐다고 한다', async () => {
    await openAt(
      run말고({
        steps: { at: 'master', done: ['pick'] },
        items: [
          {
            id: 'i1',
            kind: 'test_run',
            target_id: 't1',
            label: '시편 A',
            detail: 'parsed',
            facts: { master_curves: 1, temperature_steps: 5 },
            missing: false,
            note: null,
            added_at: '2026-09-01T00:00:00Z',
          },
        ],
      })
    )
    expect(
      within(await screen.findByLabelText('이 단계 상태')).getByText(/마스터커브가 있습니다/)
    ).toBeInTheDocument()
  })

  it('됨으로 표시했어도 안 끝났으면 그렇게 적는다', async () => {
    // **조용히 넘어가는 것이 이 화면에서 가장 나쁘다** — 표시만 보고 다음 사람이
    // 이어받으면 안 겹친 시험이 그대로 피팅으로 간다.
    await openAt(run말고({ steps: { at: 'fit', done: ['pick', 'master'] } }))
    expect(await screen.findByText('아직 남았습니다')).toBeInTheDocument()
  })

  it('막지는 않는다', async () => {
    // 워크벤치는 진행자이지 문지기가 아니다(ADR 0024). 화면 밖에서 이미 한 일을
    // 여기가 못 보는 경우가 늘 있다.
    await openAt(run말고({ steps: { at: 'master', done: ['pick'] } }))
    expect(screen.getByRole('button', { name: /다음: 글로벌 피팅/ })).toBeEnabled()
  })
})

describe('담고 나서 돌아오면', () => {
  it('그 작업이 열린다', async () => {
    // **목록으로 떨어뜨리면 방금 담은 작업을 다시 골라야 한다** — 진행 중인 것이
    // 여럿이면 어느 것이었는지 헷갈린다. 목록 화면의 「워크벤치로」 가 이 주소를 준다.
    run.mockResolvedValue(DETAIL)
    runs.mockResolvedValue([DETAIL, { ...DETAIL, id: 'r2', title: '도어트림 검토' }])
    show('/w/metal/workbench?run=r1')
    expect(await screen.findByLabelText('바구니')).toBeInTheDocument()
    expect(run).toHaveBeenCalledWith('r1')
  })

  it('모르는 작업이면 목록을 보여 준다', async () => {
    // 남이 끝냈거나 지운 작업의 주소를 눌렀을 수 있다. **빈 화면으로 두지 않는다.**
    run.mockRejectedValue(new Error('없습니다'))
    show('/w/metal/workbench?run=없는것')
    expect(await screen.findByText('해석에 쓸 물성 갖추기')).toBeInTheDocument()
  })
})

describe('담아 둔 카드로 바로 내보낸다', () => {
  it('내보내기 단계에 묶음 띠가 선다', async () => {
    // **카드 목록으로 보내 다시 고르게 하면 담아 둔 값이 그 자리에서 버려진다.**
    // 띠는 카드 화면의 것을 그대로 세운다 — 여기서 다시 만들면 형식·단위계 안내가
    // 두 벌로 갈린다.
    const detail = {
      ...DETAIL,
      steps: { at: 'export', done: ['scope', 'survey', 'collect'] },
      item_count: 1,
      items: [
        {
          id: 'i1',
          kind: 'card',
          target_id: 'c1',
          label: '점탄성 Prony',
          detail: 'EPDM · published',
          facts: { published: 1 },
          material_id: 'm1',
          missing: false,
          note: null,
          added_at: '2026-09-01T00:00:00Z',
        },
      ],
    }
    run.mockResolvedValue(detail)
    runs.mockResolvedValue([detail])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    expect(await screen.findByLabelText('묶음 내보내기')).toBeInTheDocument()
    expect(screen.getByText(/1장 골랐습니다/)).toBeInTheDocument()
  })
})

describe('할 자리로 데려간다', () => {
  const openAt = async (detail: Record<string, unknown>) => {
    run.mockResolvedValue(detail)
    runs.mockResolvedValue([detail])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    await screen.findByLabelText('단계')
  }

  it('담는 단계는 그 목록으로 가는 링크를 준다', async () => {
    // **「담는 단추는 그 목록 화면에 있습니다」 만 적으면 그 화면을 사람이 찾아야
    // 한다.** 그러면 안 담는다 — 실제로 그렇게 걸렸다.
    await openAt(run말고({ steps: { at: 'pick', done: [] }, items: [], item_count: 0 }))
    expect(screen.getByRole('link', { name: '시험 목록' })).toHaveAttribute('href', '/tests')
    // 조사도 표에서 읽은 낱말에 맞춘다 — 「시험 를 담습니다」 가 나오면 안 된다.
    expect(screen.getAllByText(/시험을/).length).toBeGreaterThan(0)
  })

  it('남은 시험을 누르면 그 시험으로 간다', async () => {
    await openAt(run말고({ steps: { at: 'master', done: ['pick'] } }))
    const status = within(await screen.findByLabelText('이 단계 상태'))
    expect(status.getByRole('link', { name: '시편 B' })).toHaveAttribute(
      'href',
      '/test-runs/시편 B'
    )
  })

  it('글로벌 피팅은 그 시험의 재료로 데려간다', async () => {
    // 피팅은 재료 화면에 있는데(ADR 0020) 바구니에는 시험이 담긴다 — 서버가 준
    // `material_id` 가 없으면 사람이 재료를 이름으로 찾아 들어가야 한다.
    await openAt(run말고({ steps: { at: 'fit', done: ['pick', 'master'] } }))
    expect(await screen.findByRole('link', { name: /이 시험의 재료로/ })).toHaveAttribute(
      'href',
      '/materials/m1'
    )
  })

  it('바구니의 줄에서 그 대상으로 간다', async () => {
    await openAt(run말고({ steps: { at: 'pick', done: [] } }))
    const basket = within(screen.getByLabelText('바구니'))
    expect(basket.getByRole('link', { name: '시편 A' })).toHaveAttribute(
      'href',
      '/test-runs/시편 A'
    )
  })
})

describe('작업 안에서', () => {
  const open = async () => {
    runs.mockResolvedValue([DETAIL])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    await screen.findByLabelText('단계')
  }

  it('다음을 누르면 진행이 서버에 적힌다', async () => {
    // **서버가 진행을 들고 있어야 다른 사람이 이어서 한다**(ADR 0025).
    await open()
    await userEvent.click(screen.getByRole('button', { name: /다음: 무엇이 있나/ }))
    await waitFor(() => expect(patch).toHaveBeenCalled())
    const [, body] = patch.mock.calls[0]
    expect((body as { steps: { at: string; done: string[] } }).steps.at).toBe('survey')
    expect((body as { steps: { done: string[] } }).steps.done).toContain('scope')
  })

  it('사라진 것도 줄을 지킨다', async () => {
    run.mockResolvedValue({
      ...DETAIL,
      item_count: 2,
      items: [
        {
          id: 'i1',
          kind: 'card',
          target_id: 'c1',
          label: '인장 MD',
          detail: 'SECC · draft',
          missing: false,
          note: null,
          added_at: '2026-09-01T00:00:00Z',
        },
        {
          id: 'i2',
          kind: 'test_run',
          target_id: 't1',
          label: '사라졌습니다',
          detail: null,
          missing: true,
          note: null,
          added_at: '2026-09-01T00:00:00Z',
        },
      ],
    })
    await open()
    const basket = within(screen.getByLabelText('바구니'))
    expect(basket.getByText('인장 MD')).toBeInTheDocument()
    expect(basket.getByText('사라졌습니다')).toBeInTheDocument()
  })

  it('모르는 워크플로면 이어서 밀지 않는다', async () => {
    // **반쯤 읽어 미는 것이 더 나쁘다.** 담긴 것은 그대로 보여 준다.
    run.mockResolvedValue({ ...DETAIL, workflow_key: '없어진워크플로' })
    runs.mockResolvedValue([{ ...DETAIL, workflow_key: '없어진워크플로' }])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    expect(await screen.findByText(/지금 화면이 모릅니다/)).toBeInTheDocument()
    expect(screen.getByLabelText('바구니')).toBeInTheDocument()
  })
})
