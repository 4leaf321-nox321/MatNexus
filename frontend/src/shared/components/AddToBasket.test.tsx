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

import { render, screen, waitFor } from '@testing-library/react'
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
    expect(screen.getByText('2건 담았습니다')).toBeInTheDocument()
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

  it('고른 것이 없으면 못 누른다', async () => {
    show([])
    expect(await screen.findByRole('button', { name: /담기/ })).toBeDisabled()
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

  it('담고 나면 그 작업을 기억한다', async () => {
    // 다음 화면에서도 같은 작업에 담긴다 — 목록을 오가며 모으는 것이 이 단추의 쓰임이다.
    show()
    await userEvent.click(await screen.findByRole('button', { name: /담기/ }))
    await waitFor(() => expect(window.localStorage.getItem('matnexus.basket.active')).toBe('r1'))
  })
})
