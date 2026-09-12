/**
 * VOC 한 건 — **절차의 단추는 서버가 말한 것만 선다.**
 *
 *   `allowed` 에 있는 것만 단추다        관리자와 낸 사람이 다르고 상태마다 다르다
 *   말이 필요한 곳은 말 없이 안 눌린다    「해결」 만 찍힌 건은 무엇이 바뀌었는지 모른다
 *   이력이 시간순으로 흐른다             등록·옮김·댓글이 구별된다
 *   고치기·삭제는 `can_edit` 가 정한다    이름으로 짐작하지 않는다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import VocDetailPage from '@/modules/voc/VocDetailPage'

const get = vi.fn()
const event = vi.fn()
const remove = vi.fn()
const removeEvent = vi.fn()
const updateEvent = vi.fn()

vi.mock('@/modules/voc/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/voc/api')>()),
  vocApi: {
    get: (id: string) => get(id),
    event: (...args: unknown[]) => event(...args),
    remove: (id: string) => remove(id),
    removeEvent: (...args: unknown[]) => removeEvent(...args),
    updateEvent: (...args: unknown[]) => updateEvent(...args),
    update: vi.fn(),
  },
}))

const registered = {
  id: 'e-1',
  at: '2026-08-27T10:00:00Z',
  by: '홍길동',
  from_status: null,
  to_status: 'open',
  to_status_label: '등록',
  note: null,
}

const detail = (over: Record<string, unknown> = {}) => ({
  id: 'voc-1',
  seq: 12,
  title: '목록이 느려요',
  body: '시험 목록이 느립니다',
  status: 'open',
  status_label: '등록',
  page_path: '/w/metal/tests',
  created_at: '2026-08-27T10:00:00Z',
  created_by: '홍길동',
  status_at: '2026-08-27T10:00:00Z',
  status_by: '홍길동',
  is_mine: true,
  can_edit: true,
  event_count: 0,
  events: [registered],
  allowed: [],
  allowed_labels: {},
  note_required: [],
  ...over,
})

async function show(body: unknown) {
  get.mockResolvedValue(body)
  render(
    <MemoryRouter initialEntries={['/voc/voc-1']}>
      <Routes>
        <Route path="/voc/:id" element={<VocDetailPage />} />
        <Route path="/voc" element={<p>목록으로 왔다</p>} />
      </Routes>
    </MemoryRouter>
  )
  await screen.findByText('목록이 느려요')
}

describe('VOC 상세', () => {
  beforeEach(() => {
    get.mockReset()
    event.mockReset()
    remove.mockReset()
    event.mockResolvedValue(detail())
    remove.mockResolvedValue(undefined)
  })

  it('낸 사람은 등록 상태에서 옮길 단추가 없고, 말만 남길 수 있다', async () => {
    const user = userEvent.setup()
    await show(detail())
    expect(screen.queryByRole('button', { name: /옮김|접수|처리 시작|반려/ })).toBeNull()
    const say = screen.getByRole('button', { name: '말만 남기기' })
    expect(say).toBeDisabled()

    await user.type(screen.getByLabelText('댓글 등록'), '덧붙입니다')
    await user.click(say)
    await waitFor(() =>
      expect(event).toHaveBeenCalledWith('voc-1', { status: null, note: '덧붙입니다' })
    )
  })

  it('관리자에게는 서버가 말한 단추가 서고, 말이 필요한 것은 말 없이 안 눌린다', async () => {
    const user = userEvent.setup()
    await show(
      detail({
        is_mine: false,
        allowed: ['accepted', 'in_progress', 'resolved', 'rejected'],
        allowed_labels: {
          accepted: '접수',
          in_progress: '처리 시작',
          resolved: '해결로 옮김',
          rejected: '반려',
        },
        note_required: ['resolved', 'rejected'],
      })
    )
    expect(screen.getByRole('button', { name: '접수' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '해결로 옮김' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '반려' })).toBeDisabled()

    await user.type(screen.getByLabelText('댓글 등록'), '다음 배포에 반영')
    expect(screen.getByRole('button', { name: '해결로 옮김' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: '해결로 옮김' }))
    await waitFor(() =>
      expect(event).toHaveBeenCalledWith('voc-1', {
        status: 'resolved',
        note: '다음 배포에 반영',
      })
    )
  })

  it('이력이 시간순으로 흐르고 등록·옮김·댓글이 구별된다', async () => {
    await show(
      detail({
        status: 'resolved',
        status_label: '해결',
        events: [
          registered,
          {
            id: 'e-2',
            at: '2026-08-27T11:00:00Z',
            by: '김철수',
            from_status: 'open',
            to_status: 'open',
            to_status_label: '등록',
            note: '저도 같은 증상입니다',
          },
          {
            id: 'e-3',
            at: '2026-08-28T09:00:00Z',
            by: '관리자',
            from_status: 'open',
            to_status: 'resolved',
            to_status_label: '해결',
            note: '다음 배포에 반영',
          },
        ],
      })
    )
    const items = within(screen.getByRole('list', { name: '이력' })).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(within(items[0]).getByText('등록')).toBeInTheDocument()
    expect(within(items[1]).getByText('댓글')).toBeInTheDocument()
    expect(within(items[1]).getByText('저도 같은 증상입니다')).toBeInTheDocument()
    expect(within(items[2]).getByText('해결 로 옮김')).toBeInTheDocument()
    expect(within(items[2]).getByText('관리자')).toBeInTheDocument()
  })

  it('관리자만 이력 줄을 지울 수 있고, 등록 줄에는 단추가 없다', async () => {
    const moved = {
      id: 'e-3',
      at: '2026-08-28T09:00:00Z',
      by: '관리자',
      from_status: 'in_progress',
      to_status: 'resolved',
      to_status_label: '해결',
      note: '실수로 눌렀다',
    }
    await show(detail({ events: [registered, moved], can_delete_events: false }))
    expect(screen.queryByRole('button', { name: '이력 삭제' })).toBeNull()

    removeEvent.mockResolvedValue(detail({ events: [registered] }))
    await show(detail({ events: [registered, moved], can_delete_events: true }))
    const buttons = screen.getAllByRole('button', { name: '이력 삭제' })
    expect(buttons).toHaveLength(1)
    await userEvent.click(buttons[0])
    expect(screen.getByRole('dialog')).toHaveTextContent('해결 로 옮김')
    expect(screen.getByRole('dialog')).toHaveTextContent('실수로 눌렀다')
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(removeEvent).toHaveBeenCalledWith('voc-1', 'e-3'))
  })

  it('관리자는 이력의 말을 고친다 — 상태 이동은 그대로', async () => {
    const moved = {
      id: 'e-3',
      at: '2026-08-28T09:00:00Z',
      by: '관리자',
      from_status: 'in_progress',
      to_status: 'resolved',
      to_status_label: '해결',
      note: '임시',
    }
    updateEvent.mockResolvedValue(detail({ events: [registered, moved] }))
    await show(detail({ events: [registered, moved], can_delete_events: true }))
    await userEvent.click(screen.getByRole('button', { name: '이력 편집' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('해결 로 옮김')
    const box = within(dialog).getByLabelText('말')
    expect(box).toHaveValue('임시')
    await userEvent.clear(box)
    await userEvent.click(within(dialog).getByRole('button', { name: '저장' }))
    expect(updateEvent).not.toHaveBeenCalled()
    await userEvent.type(box, '원본 교체 기능으로 해결')
    await userEvent.click(within(dialog).getByRole('button', { name: '저장' }))
    await waitFor(() =>
      expect(updateEvent).toHaveBeenCalledWith('voc-1', 'e-3', '원본 교체 기능으로 해결')
    )
  })

  it('고치기·삭제는 can_edit 가 정한다 — 이름이 같아도 안 된다', async () => {
    await show(detail({ is_mine: false, created_by: '홍길동', can_edit: false }))
    expect(screen.queryByRole('button', { name: '편집' })).toBeNull()
    expect(screen.queryByRole('button', { name: '삭제' })).toBeNull()
  })

  it('지우기 전에 이력이 함께 사라진다고 묻고, 지우면 목록으로 간다', async () => {
    const user = userEvent.setup()
    await show(detail())
    await user.click(screen.getByRole('button', { name: '삭제' }))
    expect(await screen.findByText(/이력 1건과 함께/)).toBeInTheDocument()
    expect(remove).not.toHaveBeenCalled()

    // 확인 창의 「삭제」 — 머리의 것과 가른다.
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith('voc-1'))
    expect(await screen.findByText('목록으로 왔다')).toBeInTheDocument()
  })
})
