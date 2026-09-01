/**
 * 워크벤치 — **고르고, 담고, 어디까지 왔는지 안다**(ADR 0024·0025).
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   무엇을 할지 먼저 고른다      워크플로 목록이 곧 「무엇을 할 수 있나」 다
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

vi.mock('@/modules/workbench/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/workbench/api')>()),
  workbenchApi: {
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

function show() {
  render(
    <MemoryRouter>
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
