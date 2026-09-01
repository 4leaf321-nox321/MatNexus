/**
 * 「담기」 — **어디에 담기는지 보이는가.**
 *
 * 이 단추가 잘못 담으면 사람은 담긴 것을 찾으러 다녀야 하고, 한 번 그러면 다시 안
 * 쓴다. 그래서 지키는 것이 셋이다.
 *
 *   대상 이름을 늘 적는다        숨기면 담고 나서 찾아야 한다
 *   작업이 없으면 만들라고 한다   꺼진 단추만 두면 고장으로 읽힌다
 *   기억해 둔 작업이 없어졌으면   진행 중인 것으로 갈아탄다 — 끝난 작업에 담지 않는다
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AddToBasket } from '@/shared/components/AddToBasket'

const runs = vi.fn()
const add = vi.fn()

vi.mock('@/shared/api/basket', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/basket')>()),
  basketApi: {
    runs: (...args: unknown[]) => runs(...args),
    add: (...args: unknown[]) => add(...args),
  },
}))

// 부서는 「내 부서」 로 정해진다 — 이 단추가 부서 스코프 밖 화면에도 붙기 때문이다.
vi.mock('@/shared/auth/AuthContext', () => ({
  useMaybeAuth: () => ({ user: { home_workspace_slug: 'metal', memberships: [] } }),
}))

const RUN = {
  id: 'r1',
  title: 'EPDM 도어씰 2026-09',
  workflow_key: 'analysis_deck',
  status: 'running',
  item_count: 0,
  workspace_id: 'w1',
  owner_id: 'u1',
  owner_name: '박용진',
  steps: {},
  note: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  finished_at: null,
}

function show(ids = ['c1']) {
  render(
    <MemoryRouter>
      <AddToBasket kind="card" ids={ids} workspaceSlug="metal" />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  runs.mockResolvedValue([RUN])
  add.mockResolvedValue([])
})

describe('어디에 담기는지', () => {
  it('단추에 작업 이름을 적는다', async () => {
    show()
    expect(await screen.findByRole('button', { name: /「EPDM 도어씰 2026-09」에 담기/ })).toBeTruthy()
  })

  it('누르면 그 작업에 담는다', async () => {
    show(['c1', 'c2'])
    await userEvent.click(await screen.findByRole('button', { name: /담기/ }))
    await waitFor(() => expect(add).toHaveBeenCalledWith('r1', 'card', ['c1', 'c2']))
    expect(screen.getByText(/2건 담았습니다/)).toBeInTheDocument()
  })

  it('여럿이면 고를 수 있다', async () => {
    runs.mockResolvedValue([RUN, { ...RUN, id: 'r2', title: '도어트림 검토' }])
    show()
    await userEvent.click(await screen.findByLabelText('담을 작업 고르기'))
    await userEvent.click(await screen.findByText('도어트림 검토'))
    await userEvent.click(screen.getByRole('button', { name: /「도어트림 검토」에 담기/ }))
    await waitFor(() => expect(add).toHaveBeenCalledWith('r2', 'card', ['c1']))
  })
})

describe('담을 데가 없을 때', () => {
  it('작업을 시작하라고 말한다', async () => {
    // **꺼진 단추만 두면 고장으로 읽힌다.**
    runs.mockResolvedValue([])
    show()
    expect(await screen.findByText(/워크벤치에서 작업을 시작/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /담기/ })).toBeNull()
  })

  it('고른 것이 없으면 아예 안 뜬다', () => {
    // **떠 있는 것은 무언가를 가린다.** 할 일이 없는데 떠 있으면 그냥 방해물이다.
    show([])
    expect(screen.queryByLabelText('담기')).toBeNull()
  })
})

describe('끌어서 옮긴다', () => {
  // 떠 있는 패널은 **하필 지금 보려는 줄을 가릴 수 있다.** 못 치우면 방해물이 된다.
  /** 손잡이를 잡고 `dx·dy` 만큼 끈다. 끌기 전 자리를 함께 돌려준다. */
  const drag = async (dx: number, dy: number) => {
    const panel = await screen.findByLabelText('담기')
    const from = { x: Number.parseInt(panel.style.left), y: Number.parseInt(panel.style.top) }
    fireEvent.pointerDown(screen.getByLabelText('끌어서 옮기기'), { clientX: 500, clientY: 500 })
    fireEvent.pointerMove(window, { clientX: 500 + dx, clientY: 500 + dy })
    fireEvent.pointerUp(window)
    return from
  }

  it('끈 만큼만 움직인다', async () => {
    // **손잡이를 쥔 지점을 유지한다** — 잡는 순간 패널이 커서로 튀면 옮기기 어렵다.
    show()
    const from = await drag(-200, -150)
    expect(screen.getByLabelText('담기')).toHaveStyle({
      left: `${from.x - 200}px`,
      top: `${from.y - 150}px`,
    })
  })

  it('다음에도 그 자리에서 뜬다', async () => {
    // 매번 같은 데로 돌아오면 매번 다시 치워야 한다.
    show()
    const from = await drag(-120, -90)
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem('matnexus.basket.spot')!)).toMatchObject({
        x: from.x - 120,
        y: from.y - 90,
      })
    )
  })

  it('창 밖의 자리는 안으로 되돌린다', async () => {
    // 창을 줄였거나 큰 화면에서 옮겨 뒀으면 기억한 자리가 화면 밖이다 —
    // **그대로 쓰면 패널이 안 보이고, 그것은 없어진 것과 구별이 안 된다.**
    window.localStorage.setItem('matnexus.basket.spot', JSON.stringify({ x: 9000, y: 9000 }))
    show()
    const panel = await screen.findByLabelText('담기')
    expect(Number.parseInt(panel.style.left)).toBeLessThan(window.innerWidth)
    expect(Number.parseInt(panel.style.top)).toBeLessThan(window.innerHeight)
  })
})

describe('기억해 둔 작업', () => {
  it('없어졌으면 진행 중인 것으로 갈아탄다', async () => {
    // 끝난 작업이나 남의 부서 것이 기억돼 있을 수 있다 — 그대로 쓰면 담기가
    // 조용히 실패하거나, 더 나쁘게 엉뚱한 데로 간다.
    window.localStorage.setItem('matnexus.basket.active', '없어진작업')
    show()
    await userEvent.click(await screen.findByRole('button', { name: /담기/ }))
    await waitFor(() => expect(add).toHaveBeenCalledWith('r1', 'card', ['c1']))
  })

  it('담고 나면 그 작업으로 돌아가는 길을 준다', async () => {
    // **담아 놓고 어디로 갈지 모른 채 서지 않게 한다.** 워크벤치 첫 화면으로
    // 보내면 방금 담은 작업을 다시 골라야 한다 — 진행 중인 것이 여럿이면 어느
    // 것이었는지 헷갈린다.
    show()
    await userEvent.click(await screen.findByRole('button', { name: /담기/ }))
    const back = await screen.findByRole('link', { name: '워크벤치로' })
    expect(back).toHaveAttribute('href', '/w/metal/workbench?run=r1')
  })

  it('담고 나면 그 작업을 기억한다', async () => {
    // 다음 화면에서도 같은 작업에 담긴다 — 목록을 오가며 모으는 것이 이 단추의 쓰임이다.
    show()
    await userEvent.click(await screen.findByRole('button', { name: /담기/ }))
    await waitFor(() => expect(window.localStorage.getItem('matnexus.basket.active')).toBe('r1'))
  })
})
