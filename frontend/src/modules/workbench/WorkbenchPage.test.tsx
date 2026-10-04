/**
 * 워크벤치 — **업무를 고르고, 담고, 어디까지 왔는지 안다**(ADR 0024 · 0025 · 0058).
 *
 * 여기서 지키는 것.
 *
 *   무엇을 할지 묶음별로 고른다   업무 목록이 곧 「무엇을 할 수 있나」 다
 *   남은 일을 이름으로 말한다     세기만 하면 어느 것인지 찾으러 다녀야 한다
 *   전용 화면은 담긴 것을 받는다   도메인 화면에 시험 id · 재료 id 를 건넨다
 *   옛 이름의 작업도 열린다       서버에 그 이름으로 적힌 작업이 있다
 *   다음 업무로 담은 것을 넘긴다   다시 고르게 하면 고른 것이 버려진다
 *   이어서 하기가 먼저 보인다     어제 것이 아래에 묻히면 서버에 둔 뜻이 없다
 *   사라진 것도 줄을 지킨다       조용히 빠지면 「여덟이 왜 일곱이지」 가 된다
 *   모르는 워크플로는 밀지 않는다  반쯤 읽어 이어서 미는 것이 더 나쁘다
 *
 * 전용 화면 자체(채택 검토대 · 골라 담기 …)는 그 모듈의 시험이 본다. 여기서는 그 자리에
 * 무엇을 건네는지만 본다 — 그래서 도메인 화면을 받은 것을 그대로 적는 그림으로 바꿔 둔다.
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
const add = vi.fn()

vi.mock('@/shared/api/basket', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/basket')>()),
  basketApi: {
    runs: (...args: unknown[]) => runs(...args),
    run: (...args: unknown[]) => run(...args),
    create: (...args: unknown[]) => create(...args),
    patch: (...args: unknown[]) => patch(...args),
    remove: (...args: unknown[]) => remove(...args),
    add: (...args: unknown[]) => add(...args),
  },
}))

// 도메인 화면 — 받은 것을 적기만 한다.
vi.mock('@/modules/tests/RunCollector', () => ({
  RunCollector: (props: {
    processing?: string
    taken: string[]
    onPick: (ids: string[]) => Promise<void>
  }) => (
    <div aria-label="골라 담기">
      <span>처음 거르기 {props.processing ?? '전부'}</span>
      <span>담김 {props.taken.join(',')}</span>
      <button type="button" onClick={() => void props.onPick(['t9'])}>
        t9 담기
      </button>
    </div>
  ),
}))
vi.mock('@/modules/processing/AdoptionBoard', () => ({
  AdoptionBoard: (props: { testRunIds: string[] }) => (
    <div aria-label="채택 검토대">견줄 시험 {props.testRunIds.join(',')}</div>
  ),
}))
vi.mock('@/modules/processing/BatchPanel', () => ({
  BatchByType: (props: { testRunIds: string[] }) => (
    <div aria-label="한 번에 처리">처리할 시험 {props.testRunIds.join(',')}</div>
  ),
}))
vi.mock('@/modules/fitting/CardMaker', () => ({
  CardMaterialPick: (props: {
    current: { id: string; label: string } | null
    suggested: { id: string; label: string }[]
    onPick: (id: string) => Promise<void>
  }) => (
    <div aria-label="재료 고르기">
      <span>지금 {props.current?.label ?? '없음'}</span>
      <span>권함 {props.suggested.map((one) => one.label).join(',')}</span>
      <button type="button" onClick={() => void props.onPick('m2')}>
        m2 로
      </button>
    </div>
  ),
}))
vi.mock('@/modules/fitting/FittingPanel', () => ({
  FittingPanel: (props: { materialId: string }) => <div>카드 패널 {props.materialId}</div>,
}))
vi.mock('@/modules/fitting/DeckReadinessTable', () => ({
  DeckReadinessTable: (props: { materialId: string }) => <div>준비도 {props.materialId}</div>,
}))
vi.mock('@/modules/fitting/BomDeckPage', () => ({
  BomDeck: () => <div>BOM 덱 본문</div>,
}))

const DETAIL = {
  id: 'r1',
  workspace_id: 'w1',
  owner_id: 'u1',
  owner_name: '박용진',
  workflow_key: 'bundle_export',
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

function testRun(label: string, facts: Record<string, number>, over: Record<string, unknown> = {}) {
  return {
    id: `i-${label}`,
    kind: 'test_run',
    target_id: label,
    label,
    detail: '완료',
    facts,
    material_id: 'm1',
    material_label: 'EPDM-70',
    missing: false,
    note: null,
    added_at: '2026-09-01T00:00:00Z',
    ...over,
  }
}

function show(at = '/workbench') {
  render(
    <MemoryRouter initialEntries={[at]}>
      <WorkbenchPage />
    </MemoryRouter>
  )
}

/** 작업 하나를 「계속」 에서 연다. */
async function openRun(detail: Record<string, unknown>) {
  run.mockResolvedValue(detail)
  runs.mockResolvedValue([detail])
  show()
  await userEvent.click(await screen.findByText(String(detail.title)))
  await screen.findByLabelText('단계')
}

beforeEach(() => {
  vi.clearAllMocks()
  runs.mockResolvedValue([])
  run.mockResolvedValue(DETAIL)
  create.mockResolvedValue(DETAIL)
  patch.mockResolvedValue(DETAIL)
  remove.mockResolvedValue(undefined)
  add.mockResolvedValue([])
})

describe('무엇을 할지 묶음별로 고른다', () => {
  it('묶음마다 업무가 서고, 전용 화면인지 안내인지 미리 보인다', async () => {
    show()
    const tests = await screen.findByRole('region', { name: '시험 데이터' })
    expect(within(tests).getByText('계산된 시험 데이터 한번에 채택하기')).toBeInTheDocument()
    expect(within(tests).getByText('시험 데이터 한번에 처리하기')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '물성 카드' })).toHaveTextContent('물성 카드 하나 만들기')
    expect(screen.getByRole('region', { name: '해석 덱' })).toHaveTextContent(
      '부품표(BOM)로 여러 카드를 한 덱에'
    )
    expect(screen.getByRole('region', { name: '장비 · 형식' })).toHaveTextContent('새 장비 파일 연결')

    const adopt = screen.getByText('계산된 시험 데이터 한번에 채택하기').closest('div')!.parentElement!
    expect(within(adopt).getByText('전용 화면')).toBeInTheDocument()
    const review = screen.getByText('카드 확정 전 검토하기').closest('div')!.parentElement!
    expect(within(review).getByText('안내')).toBeInTheDocument()
  })

  it('단계를 미리 보여 준다', async () => {
    // **시작하고 나서 알면 되돌리는 값이 든다.**
    show()
    const card = (await screen.findByText('여러 카드를 한 묶음으로 내보내기')).closest('div')!
      .parentElement!
    expect(within(card).getByText(/1\. 무엇에 쓰나/)).toBeInTheDocument()
  })

  it('이름을 적어 시작하면 그 업무로 만든다', async () => {
    show()
    const name = await screen.findByLabelText('계산된 시험 데이터 한번에 채택하기 작업 이름')
    await userEvent.type(name, 'SECC 10월')
    await userEvent.click(
      within(name.closest('div')!.parentElement!).getByRole('button', { name: /시작/ })
    )
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({ workflow_key: 'adopt_many', title: 'SECC 10월' })
  })

  it('이름을 비워도 시작은 된다', async () => {
    // **막지 않는다.** 이름이 없으면 업무 이름과 날짜로 짓는다.
    show()
    const buttons = await screen.findAllByRole('button', { name: /시작/ })
    await userEvent.click(buttons[0])
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0].title).toBeTruthy()
  })
})

describe('계속', () => {
  it('진행 중인 작업은 업무 목록과 따로, 옆 열에 선다', async () => {
    // **하는 일이 많아져도 새 일을 시작할 카드가 밀리지 않는다**(2026-10-04 지적) — 전에는
    // 「계속」 이 업무 목록 위에 쌓여, 작업이 늘수록 카드가 아래로 내려갔다.
    runs.mockResolvedValue([
      { ...DETAIL, item_count: 3 },
      ...Array.from({ length: 12 }, (_, at) => ({ ...DETAIL, id: `r${at + 2}`, title: `작업 ${at}` })),
    ])
    show()
    const resume = within(await screen.findByRole('complementary', { name: '계속' }))
    expect(await resume.findByText('EPDM 도어씰 2026-09')).toBeInTheDocument()
    expect(resume.getByText(/담은 것 3/)).toBeInTheDocument()
    expect(resume.getByText('13')).toBeInTheDocument()
    // 업무 카드는 그 열 밖에 있다.
    expect(resume.queryByText('계산된 시험 데이터 한번에 채택하기')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: '시험 데이터' })).toBeInTheDocument()
  })

  it('이어 할 것이 없으면 그렇다고 말하고, 부서 범위를 넓혀 본다', async () => {
    show()
    const resume = within(await screen.findByRole('complementary', { name: '계속' }))
    expect(await resume.findByText(/이어 할 작업이 없습니다/)).toBeInTheDocument()
    await userEvent.click(resume.getByRole('button', { name: '모든 부서' }))
    await waitFor(() => expect(runs).toHaveBeenLastCalledWith('running', 'all'))
    expect(resume.getByRole('button', { name: '모든 부서' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('누르면 그 작업을 연다', async () => {
    runs.mockResolvedValue([DETAIL])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    await waitFor(() => expect(run).toHaveBeenCalledWith('r1'))
    expect(await screen.findByLabelText('바구니')).toBeInTheDocument()
  })
})

describe('옛 이름으로 적힌 작업 (ADR 0058)', () => {
  it('옛 업무 이름이면 지금 업무로 열고 그렇다고 말한다', async () => {
    // **서버에 그 이름으로 적힌 작업이 있다** — 「모르는 워크플로」 로 세우면 이어 할 수 없다.
    await openRun({ ...DETAIL, workflow_key: 'analysis_deck' })
    expect(screen.getByText(/예전 업무 이름/)).toBeInTheDocument()
    expect(screen.getAllByText('여러 카드를 한 묶음으로 내보내기').length).toBeGreaterThan(0)
    expect(screen.queryByText(/지금 화면이 모릅니다/)).not.toBeInTheDocument()
  })

  it('옛 단계 이름은 합친 단계로 옮겨 연다 — 1단계로 되돌아가지 않는다', async () => {
    // 「DMA 한 벌로 점탄성 계수 내기」 의 마스터커브 단계 → 「무엇이 나오나」.
    await openRun({
      ...DETAIL,
      workflow_key: 'viscoelastic_set',
      steps: { at: 'master', done: ['pick'] },
      items: [testRun('시편 A', { master_curves: 1 })],
    })
    expect(screen.getByRole('heading', { name: /2\. 무엇이 나오나/ })).toBeInTheDocument()
    expect(screen.queryByText(/단계 구성이 바뀌었습니다/)).not.toBeInTheDocument()
    // 그 작업은 시험을 담았다 — **담은 시험의 재료로** 준비도를 세운다.
    expect(await screen.findByText('준비도 m1')).toBeInTheDocument()
  })
})

describe('남은 일을 말한다', () => {
  it('안 읽힌 시험의 이름을 대고 그 시험으로 데려간다', async () => {
    await openRun({
      ...DETAIL,
      workflow_key: 'process_many',
      steps: { at: 'read', done: ['pick'] },
      items: [testRun('시편 A', { parsed: 1 }), testRun('시편 B', { parsed: 0 })],
    })
    const status = within(await screen.findByLabelText('이 단계 상태'))
    expect(status.getByText(/1건이 아직 안 읽혔거나 실패했습니다/)).toBeInTheDocument()
    expect(status.getByRole('link', { name: '시편 B' })).toHaveAttribute('href', '/test-runs/시편 B')
    expect(status.getByRole('link', { name: /형식 정의로/ })).toHaveAttribute(
      'href',
      '/settings/formats'
    )
  })

  it('됨으로 표시했어도 안 끝났으면 그렇게 적는다', async () => {
    // **조용히 넘어가는 것이 이 화면에서 가장 나쁘다** — 표시만 보고 다음 사람이
    // 이어받으면 안 읽힌 시험이 그대로 처리로 간다.
    await openRun({
      ...DETAIL,
      workflow_key: 'process_many',
      steps: { at: 'process', done: ['pick', 'read'] },
      items: [testRun('시편 A', { parsed: 1 }), testRun('시편 B', { parsed: 0 })],
    })
    expect(await screen.findByText('아직 남았습니다')).toBeInTheDocument()
  })

  it('막지는 않는다', async () => {
    // 워크벤치는 진행자이지 문지기가 아니다(ADR 0024).
    await openRun({
      ...DETAIL,
      workflow_key: 'process_many',
      steps: { at: 'read', done: ['pick'] },
      items: [testRun('시편 B', { parsed: 0 })],
    })
    expect(screen.getByRole('button', { name: /다음: 한 번에 처리/ })).toBeEnabled()
  })
})

describe('전용 화면은 담긴 것을 받는다', () => {
  const items = [
    testRun('t1', { parsed: 1, results: 1 }),
    testRun('t2', { parsed: 1, results: 1 }),
    testRun('사라진것', {}, { missing: true, label: '사라졌습니다' }),
  ]

  it('채택 검토대에 살아 있는 시험만 건넨다', async () => {
    await openRun({ ...DETAIL, workflow_key: 'adopt_many', steps: { at: 'adopt' }, items })
    expect(await screen.findByLabelText('채택 검토대')).toHaveTextContent('견줄 시험 t1,t2')
  })

  it('한 번에 처리에도 같은 시험을 건넨다', async () => {
    await openRun({ ...DETAIL, workflow_key: 'process_many', steps: { at: 'process' }, items })
    expect(await screen.findByLabelText('한 번에 처리')).toHaveTextContent('처리할 시험 t1,t2')
  })

  it('골라 담으면 바구니에 적고 다시 읽는다 — 처음 거르기는 업무가 정한다', async () => {
    await openRun({ ...DETAIL, workflow_key: 'adopt_many', steps: { at: 'pick' }, items })
    const picker = within(await screen.findByLabelText('골라 담기'))
    // 「한번에 채택하기」 는 결과는 있는데 채택 안 한 것을 먼저 세운다.
    expect(picker.getByText('처음 거르기 results')).toBeInTheDocument()
    expect(picker.getByText('담김 t1,t2')).toBeInTheDocument()
    await userEvent.click(picker.getByRole('button', { name: 't9 담기' }))
    await waitFor(() => expect(add).toHaveBeenCalledWith('r1', 'test_run', ['t9']))
    await waitFor(() => expect(run).toHaveBeenCalledTimes(2))
  })

  it('전용 화면에서 담는 단계는 목록 화면으로 보내지 않는다', async () => {
    // 그 자리에서 고르는데 「시험 목록에서 고른 뒤」 를 또 적으면 어느 쪽인지 헷갈린다.
    await openRun({ ...DETAIL, workflow_key: 'adopt_many', steps: { at: 'pick' }, items })
    await screen.findByLabelText('골라 담기')
    expect(screen.queryByRole('link', { name: '시험 목록' })).not.toBeInTheDocument()
  })

  it('재료는 하나다 — 바꾸면 앞의 재료를 빼고 담는다', async () => {
    const material = {
      ...testRun('m1', {}),
      id: 'i-m1',
      kind: 'material',
      target_id: 'm1',
      label: 'EPDM-70',
    }
    await openRun({
      ...DETAIL,
      workflow_key: 'card_one',
      steps: { at: 'material' },
      items: [material],
    })
    const pick = within(await screen.findByLabelText('재료 고르기'))
    expect(pick.getByText('지금 EPDM-70')).toBeInTheDocument()
    await userEvent.click(pick.getByRole('button', { name: 'm2 로' }))
    await waitFor(() => expect(add).toHaveBeenCalledWith('r1', 'material', ['m2']))
    expect(remove).toHaveBeenCalledWith('r1', 'i-m1')
  })

  it('카드 만들기는 그 재료의 카드 패널을 세운다', async () => {
    await openRun({
      ...DETAIL,
      workflow_key: 'card_one',
      steps: { at: 'make' },
      items: [{ ...testRun('m1', {}), kind: 'material', target_id: 'm7', label: 'PP' }],
    })
    expect(await screen.findByText('카드 패널 m7')).toBeInTheDocument()
  })

  it('담은 카드로 바로 내보낸다 — 카드 목록의 그 띠를 세운다', async () => {
    // **카드 목록으로 보내 다시 고르게 하면 담아 둔 값이 그 자리에서 버려진다.**
    await openRun({
      ...DETAIL,
      steps: { at: 'export', done: ['scope', 'survey', 'collect'] },
      items: [
        {
          id: 'i1',
          kind: 'card',
          target_id: 'c1',
          label: '점탄성 Prony',
          detail: 'EPDM · 확정',
          facts: { published: 1 },
          material_id: 'm1',
          missing: false,
          note: null,
          added_at: '2026-09-01T00:00:00Z',
        },
      ],
    })
    expect(await screen.findByLabelText('묶음 내보내기')).toBeInTheDocument()
    expect(screen.getByText(/1장 골랐습니다/)).toBeInTheDocument()
  })
})

describe('다음 업무로 담은 것을 넘긴다', () => {
  it('등록이 끝나면 담은 시험 그대로 처리 업무를 시작한다', async () => {
    // **다시 고르게 하면 고른 것이 그 자리에서 버려진다.**
    const made = { ...DETAIL, id: 'r2', workflow_key: 'process_many' }
    create.mockResolvedValue(made)
    await openRun({
      ...DETAIL,
      workflow_key: 'intake_many',
      steps: { at: 'read', done: ['upload', 'pick'] },
      items: [
        testRun('t1', { parsed: 1 }),
        testRun('사라진것', {}, { missing: true, label: '사라졌습니다' }),
      ],
    })
    run.mockResolvedValue(made)
    await userEvent.click(
      screen.getByRole('button', { name: /「시험 데이터 한번에 처리하기」 로 이어 하기/ })
    )
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({ workflow_key: 'process_many' })
    await waitFor(() => expect(add).toHaveBeenCalledWith('r2', 'test_run', ['t1']))
    // 앞 작업은 끝낸다 — 「계속」 에 같은 시험을 든 작업이 둘 서지 않게.
    await waitFor(() => expect(patch).toHaveBeenCalledWith('r1', { status: 'finished' }))
  })
})

describe('담고 나서 돌아오면', () => {
  it('그 작업이 열린다', async () => {
    // **목록으로 떨어뜨리면 방금 담은 작업을 다시 골라야 한다.**
    run.mockResolvedValue(DETAIL)
    runs.mockResolvedValue([DETAIL, { ...DETAIL, id: 'r2', title: '도어트림 검토' }])
    show('/workbench?run=r1')
    expect(await screen.findByLabelText('바구니')).toBeInTheDocument()
    expect(run).toHaveBeenCalledWith('r1')
  })

  it('모르는 작업이면 목록을 보여 준다', async () => {
    // 남이 끝냈거나 지운 작업의 주소를 눌렀을 수 있다. **빈 화면으로 두지 않는다.**
    run.mockRejectedValue(new Error('없습니다'))
    show('/workbench?run=없는것')
    expect(await screen.findByText('여러 카드를 한 묶음으로 내보내기')).toBeInTheDocument()
  })
})

describe('할 자리로 데려간다', () => {
  it('목록 화면에서 담는 단계는 그 목록으로 가는 링크를 준다', async () => {
    // **「담는 단추는 그 목록 화면에 있습니다」 만 적으면 그 화면을 사람이 찾아야
    // 한다.** 그러면 안 담는다 — 실제로 그렇게 걸렸다.
    await openRun({ ...DETAIL, steps: { at: 'scope' } })
    expect(screen.getByRole('link', { name: '재료 목록' })).toHaveAttribute(
      'href',
      '/materials?collect=material'
    )
    // 조사도 표에서 읽은 낱말에 맞춘다 — 「재료 를 담습니다」 가 나오면 안 된다.
    expect(screen.getAllByText(/재료를/).length).toBeGreaterThan(0)
  })

  it('카드 줄은 그 재료의 CAE 카드 탭으로 간다', async () => {
    // **카드는 자기 주소가 없다** — 재료의 「CAE 카드」 탭에서 펼쳐 본다.
    await openRun({
      ...DETAIL,
      workflow_key: 'review_cards',
      steps: { at: 'pick' },
      items: [
        {
          id: 'i1',
          kind: 'card',
          target_id: 'c1',
          label: '점탄성 Prony',
          detail: 'EPDM · 초안',
          facts: { published: 0 },
          material_id: 'm9',
          missing: false,
          note: null,
          added_at: '2026-09-01T00:00:00Z',
        },
      ],
    })
    const basket = within(screen.getByLabelText('바구니'))
    expect(basket.getByRole('link', { name: '점탄성 Prony' })).toHaveAttribute(
      'href',
      '/materials/m9?tab=cards'
    )
  })

  it('바구니의 시험 줄에 재료 이름이 붙는다', async () => {
    await openRun({
      ...DETAIL,
      workflow_key: 'process_many',
      steps: { at: 'read' },
      items: [testRun('시편 A', { parsed: 1 })],
    })
    const basket = within(screen.getByLabelText('바구니'))
    expect(basket.getByRole('link', { name: '시편 A' })).toHaveAttribute('href', '/test-runs/시편 A')
    expect(basket.getByText('EPDM-70')).toBeInTheDocument()
  })
})

describe('작업 안에서', () => {
  it('다음을 누르면 진행이 서버에 적힌다', async () => {
    // **서버가 진행을 들고 있어야 다른 사람이 이어서 한다**(ADR 0025).
    await openRun(DETAIL)
    await userEvent.click(screen.getByRole('button', { name: /다음: 무엇이 있나/ }))
    await waitFor(() => expect(patch).toHaveBeenCalled())
    const [, body] = patch.mock.calls[0]
    expect((body as { steps: { at: string; done: string[] } }).steps.at).toBe('survey')
    expect((body as { steps: { done: string[] } }).steps.done).toContain('scope')
  })

  it('진행 적기가 실패하면 연 작업 안에서 말한다', async () => {
    // 전에는 오류 표시가 목록 쪽에만 있어, 목록으로 돌아가기 전에는 아무것도 안 떴다(2026-10-04).
    patch.mockRejectedValueOnce(new Error('진행을 적을 권한이 없습니다'))
    await openRun(DETAIL)
    await userEvent.click(screen.getByRole('button', { name: /다음: 무엇이 있나/ }))
    expect(await screen.findByText('진행을 적을 권한이 없습니다')).toBeInTheDocument()
    expect(screen.getByLabelText('단계')).toBeInTheDocument()
  })

  it('모르는 단계로 조용히 옮기지 않는다', async () => {
    // 단계 이름이 바뀐 뒤 이어서 연 작업이 **아무 말 없이 1단계로 되돌아오면**
    // 사람은 자기가 잘못 눌렀다고 여긴다. 담긴 것은 그대로 두고 사실만 말한다.
    await openRun({ ...DETAIL, steps: { at: '없어진단계', done: ['scope'] } })
    expect(screen.getByText(/단계 구성이 바뀌었습니다/)).toBeInTheDocument()
    expect(screen.getByLabelText('바구니')).toBeInTheDocument()
  })

  it('사라진 것도 줄을 지킨다', async () => {
    await openRun({
      ...DETAIL,
      item_count: 2,
      items: [
        {
          id: 'i1',
          kind: 'card',
          target_id: 'c1',
          label: '인장 MD',
          detail: 'SECC · 초안',
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
    const basket = within(screen.getByLabelText('바구니'))
    expect(basket.getByText('인장 MD')).toBeInTheDocument()
    expect(basket.getByText('사라졌습니다')).toBeInTheDocument()
  })

  it('모르는 워크플로면 이어서 밀지 않는다', async () => {
    // **반쯤 읽어 미는 것이 더 나쁘다.** 담긴 것은 그대로 보여 준다.
    const gone = { ...DETAIL, workflow_key: '없어진워크플로' }
    run.mockResolvedValue(gone)
    runs.mockResolvedValue([gone])
    show()
    await userEvent.click(await screen.findByText('EPDM 도어씰 2026-09'))
    expect(await screen.findByText(/지금 화면이 모릅니다/)).toBeInTheDocument()
    expect(screen.getByLabelText('바구니')).toBeInTheDocument()
  })
})
