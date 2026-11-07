/**
 * VOC 게시판 — **번호·사람·날짜·상태가 한 표에 서고, 거를 수 있다.**
 *
 *   번호가 붙고 최신이 위다        「VOC 12번」 이라고 부를 수 있다
 *   상태 칩은 서버가 준 것으로 선다   상태가 늘어도 화면이 표를 안 든다
 *   거르면 서버에 그대로 묻는다     화면에서 거르면 이 쪽에 실린 것만 걸러진다
 *   최근 처리는 손댄 사람과 때다    등록만 된 건은 비워 둔다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import VocPage from '@/modules/voc/VocPage'

const list = vi.fn()
const statuses = vi.fn()
const create = vi.fn()
const attach = vi.fn()
const exportZip = vi.fn()
const contents = vi.fn()
const contentsOf = vi.fn()
const copyText = vi.fn()

vi.mock('@/shared/lib/clipboard', () => ({
  copyText: (text: string) => copyText(text),
}))

vi.mock('@/modules/voc/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/voc/api')>()),
  vocApi: {
    list: (...args: unknown[]) => list(...args),
    statuses: () => statuses(),
    create: (...args: unknown[]) => create(...args),
    attach: (...args: unknown[]) => attach(...args),
    exportZip: (...args: unknown[]) => exportZip(...args),
    contents: (...args: unknown[]) => contents(...args),
    contentsOf: (...args: unknown[]) => contentsOf(...args),
  },
}))

const item = (over: Record<string, unknown> = {}) => ({
  id: 'voc-1',
  seq: 12,
  title: '목록이 느려요',
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
  ...over,
})

const STATUSES = [
  { key: 'open', label: '등록' },
  { key: 'accepted', label: '접수' },
  { key: 'in_progress', label: '처리 중' },
  { key: 'resolved', label: '해결' },
  { key: 'closed', label: '종료' },
  { key: 'rejected', label: '반려' },
]

async function show(rows: unknown[]) {
  list.mockResolvedValue({ items: rows, total: rows.length, limit: 50, offset: 0 })
  render(
    <MemoryRouter initialEntries={['/voc']}>
      <VocPage />
    </MemoryRouter>
  )
  await waitFor(() => expect(list).toHaveBeenCalled())
  // **그려진 것을 기다린다.** 불린 것(`list` 호출)과 다시 그린 것은 다른 순간이라, 불린
  // 것만 기다리면 느린 CI 에서 아직 안 그려진 표에 대고 검사한다 — 감사 화면 시험이 CI 에서
  // 그렇게 졌고, 응답을 30ms 늦춰 돌리니 여기서도 졌다(2026-09-24).
  const first = rows[0] as { title?: string } | undefined
  if (first?.title) await screen.findAllByText(first.title)
}

/** 마지막으로 서버에 보낸 질의. */
function asked(): Record<string, unknown> {
  return (list.mock.calls.at(-1)?.[0] ?? {}) as Record<string, unknown>
}

describe('VOC 게시판', () => {
  beforeEach(() => {
    list.mockReset()
    statuses.mockReset()
    statuses.mockResolvedValue(STATUSES)
  })

  it('번호·제목·상태·올린 사람·날짜가 한 줄에 선다', async () => {
    await show([
      item(),
      item({
        id: 'voc-2',
        seq: 13,
        title: '내보내기 오류',
        status: 'resolved',
        status_label: '해결',
        created_by: '김철수',
        status_by: '관리자',
        status_at: '2026-08-28T09:00:00Z',
        is_mine: false,
        event_count: 3,
      }),
    ])
    const rows = await screen.findAllByRole('row')
    // 머리 한 줄 + 자료 두 줄
    expect(rows).toHaveLength(3)
    const second = rows[2]
    expect(within(second).getByText('13')).toBeInTheDocument()
    expect(within(second).getByRole('link', { name: '내보내기 오류' })).toHaveAttribute(
      'href',
      '/voc/voc-2'
    )
    expect(within(second).getByText('해결')).toBeInTheDocument()
    expect(within(second).getByText('김철수')).toBeInTheDocument()
    // 최근 처리 = 손댄 사람. 말이 오간 수도 보인다.
    expect(within(second).getByText(/관리자/)).toBeInTheDocument()
    expect(within(second).getByText('3')).toBeInTheDocument()
    // 등록만 된 건은 최근 처리가 비어 있다.
    expect(within(rows[1]).getByText('—')).toBeInTheDocument()
  })

  it('상태 칩은 서버가 준 것으로 서고, 누르면 서버에 묻는다', async () => {
    const user = userEvent.setup()
    await show([item()])
    const chips = await screen.findByRole('group', { name: '상태로 필터' })
    // 칩은 따로 오는 상태 목록으로 선다 — 묶음 틀(「전부」)은 그보다 먼저 선다.
    await waitFor(() =>
      expect(within(chips).getAllByRole('button')).toHaveLength(STATUSES.length + 1)
    )

    await user.click(within(chips).getByRole('button', { name: '처리 중' }))
    await waitFor(() => expect(asked().status).toBe('in_progress'))
    await user.click(within(chips).getByRole('button', { name: '전체' }))
    await waitFor(() => expect(asked().status).toBeUndefined())
  })

  it('내 것만·글자 찾기도 서버가 거른다', async () => {
    const user = userEvent.setup()
    await show([item()])
    await user.click(screen.getByLabelText('내가 낸 것만'))
    await waitFor(() => expect(asked().mine).toBe(true))

    await user.type(screen.getByLabelText('VOC 찾기'), '느려{Enter}')
    await waitFor(() => expect(asked().q).toBe('느려'))
  })

  it('거른 결과가 없으면 「없다」 가 아니라 「조건에 맞는 것이 없다」 고 말한다', async () => {
    const user = userEvent.setup()
    await show([item()])
    list.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    await user.click(await screen.findByRole('button', { name: '반려' }))
    expect(await screen.findByText(/거른 조건에 맞는 것이 없습니다/)).toBeInTheDocument()
  })
})

describe('고른 건 내려받기', () => {
  beforeEach(() => {
    list.mockReset()
    statuses.mockReset()
    statuses.mockResolvedValue(STATUSES)
    exportZip.mockReset()
    exportZip.mockResolvedValue(undefined)
  })

  it('고른 것이 있을 때만 단추가 서고, 고른 id 를 넘긴다', async () => {
    await show([item(), item({ id: 'voc-2', seq: 13, title: '두 번째' })])
    expect(screen.queryByRole('button', { name: /다운로드/ })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByLabelText('두 번째 고르기'))
    await userEvent.click(screen.getByRole('button', { name: '1건 다운로드' }))
    await waitFor(() => expect(exportZip).toHaveBeenCalledWith(['voc-2']))
  })

  it('머리 체크박스는 이 쪽 전부를 고른다', async () => {
    await show([item(), item({ id: 'voc-2', seq: 13, title: '두 번째' })])
    await screen.findByLabelText('두 번째 고르기')
    await userEvent.click(screen.getByLabelText('이 쪽 전부 고르기'))
    expect(screen.getByRole('button', { name: '2건 다운로드' })).toBeInTheDocument()
  })

  it('첨부가 있는 건은 클립과 수가 보인다', async () => {
    await show([item({ attachment_count: 2 })])
    expect(await screen.findByTitle('첨부 2개')).toHaveTextContent('2')
  })
})

describe('범위를 골라 내용 복사', () => {
  const user = () => userEvent.setup()
  const five = () =>
    [16, 15, 14, 13, 12].map((seq) => item({ id: `voc-${seq}`, seq, title: `${seq}번 글` }))

  /** 복사할 글 한 건 — 화면의 줄과 같은 번호 · 제목에 본문 · 이력. */
  const content = (seq: number) => ({
    id: `voc-${seq}`,
    seq,
    title: `${seq}번 글`,
    status: 'open',
    status_label: '등록',
    page_path: null,
    created_at: '2026-08-27T10:00:00Z',
    created_by: '홍길동',
    body: `${seq}번 본문`,
    events: [],
    attachments: [],
  })

  beforeEach(() => {
    list.mockReset()
    statuses.mockReset()
    statuses.mockResolvedValue(STATUSES)
    contents.mockReset()
    contentsOf.mockReset()
    copyText.mockReset()
    copyText.mockResolvedValue(true)
  })

  async function open(u: ReturnType<typeof userEvent.setup>, name: string | RegExp) {
    await u.click(screen.getByRole('button', { name }))
    const dialog = await screen.findByRole('dialog')
    const box = within(dialog).getByLabelText('VOC 내용') as HTMLTextAreaElement
    return { dialog, box }
  }

  it('Shift 를 누른 채 고르면 사이의 줄까지 고르고, 다시 그렇게 누르면 사이를 푼다', async () => {
    const u = user()
    await show(five())
    await u.click(screen.getByLabelText('15번 글 고르기'))
    await u.keyboard('{Shift>}')
    await u.click(screen.getByLabelText('13번 글 고르기'))
    await u.keyboard('{/Shift}')
    const checked = (seq: number) =>
      (screen.getByLabelText(`${seq}번 글 고르기`) as HTMLInputElement).checked
    expect([16, 15, 14, 13, 12].map(checked)).toEqual([false, true, true, true, false])
    expect(screen.getByRole('button', { name: '고른 3건 복사' })).toBeInTheDocument()

    // 고른 줄에서 Shift 로 누르면 푸는 쪽이다 — 마지막으로 누른 13 부터 14 까지.
    await u.keyboard('{Shift>}')
    await u.click(screen.getByLabelText('14번 글 고르기'))
    await u.keyboard('{/Shift}')
    expect([16, 15, 14, 13, 12].map(checked)).toEqual([false, true, false, false, false])
  })

  it('고른 건을 모아 보여 주고, 다 모인 뒤 누르면 그 글을 복사한다', async () => {
    const u = user()
    contentsOf.mockResolvedValue([content(15), content(14)])
    await show(five())
    await u.click(screen.getByLabelText('15번 글 고르기'))
    await u.keyboard('{Shift>}')
    await u.click(screen.getByLabelText('14번 글 고르기'))
    await u.keyboard('{/Shift}')

    const { dialog, box } = await open(u, '고른 2건 복사')
    // 데이터로 그려진 것을 기다린다 — 마지막 건의 본문까지 들어왔을 때다.
    await waitFor(() => expect(box.value).toContain('14번 본문'))
    expect(contentsOf).toHaveBeenCalledWith(['voc-15', 'voc-14'])
    expect(box.value).toContain('고른 2건')
    expect(box.value.indexOf('## 15. 15번 글')).toBeLessThan(box.value.indexOf('## 14. 14번 글'))
    expect(contents).not.toHaveBeenCalled()

    await u.click(within(dialog).getByRole('button', { name: '복사' }))
    await waitFor(() => expect(copyText).toHaveBeenCalledWith(box.value))
    expect(await within(dialog).findByRole('button', { name: '복사했습니다' })).toBeInTheDocument()
  })

  it('번호 범위는 거른 조건 안에서 모으고, 거꾸로 적으면 바로잡는다', async () => {
    const u = user()
    contents.mockImplementation(async (params: { seqFrom?: number }) => {
      const items = params.seqFrom ? [content(14), content(13)] : five().map((one) => content(one.seq))
      return { items, total: items.length, limit: 200, offset: 0 }
    })
    await show(five())
    await u.click(screen.getByRole('button', { name: '해결' }))
    await screen.findAllByText('16번 글')

    const { dialog, box } = await open(u, '내용 복사')
    // 열자마자 거른 조건 전부를 모은다.
    await waitFor(() => expect(box.value).toContain('12번 본문'))
    expect(contents).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'resolved', seqFrom: undefined, seqTo: undefined })
    )
    expect(box.value).toContain('상태 「해결」')

    await u.type(within(dialog).getByLabelText('번호 시작'), '14')
    await u.type(within(dialog).getByLabelText('번호 끝'), '13')
    // 칸만 고치고 안 모았으면 복사가 막힌다 — 글은 아직 옛 범위다.
    expect(within(dialog).getByRole('button', { name: '복사' })).toBeDisabled()
    expect(within(dialog).getByRole('alert')).toHaveTextContent('모으기')

    await u.click(within(dialog).getByRole('button', { name: '모으기' }))
    await waitFor(() => expect(box.value).toContain('번호 13~14'))
    expect(contents).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'resolved', seqFrom: 13, seqTo: 14 })
    )
    expect(box.value).not.toContain('12번 본문')
    expect((within(dialog).getByLabelText('번호 시작') as HTMLInputElement).value).toBe('13')
    expect(within(dialog).getByRole('button', { name: '복사' })).toBeEnabled()
  })

  it('고른 것이 있어도 번호 범위로 바꿔 모을 수 있다', async () => {
    const u = user()
    contentsOf.mockResolvedValue([content(16)])
    contents.mockResolvedValue({ items: [content(13)], total: 1, limit: 200, offset: 0 })
    await show(five())
    await u.click(screen.getByLabelText('16번 글 고르기'))
    const { dialog, box } = await open(u, '고른 1건 복사')
    await waitFor(() => expect(box.value).toContain('16번 본문'))

    await u.click(within(dialog).getByRole('radio', { name: '번호 범위' }))
    await waitFor(() => expect(box.value).toContain('13번 본문'))
    expect(box.value).not.toContain('16번 본문')
  })

  it('선택 해제는 다른 쪽에서 고른 것까지 푼다', async () => {
    const u = user()
    await show(five())
    await u.click(screen.getByLabelText('16번 글 고르기'))
    await u.click(screen.getByRole('button', { name: '선택 해제' }))
    expect(screen.getByRole('button', { name: '내용 복사' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /다운로드/ })).not.toBeInTheDocument()
  })
})

describe('등록할 때 파일을 붙인다', () => {
  beforeEach(() => {
    list.mockReset()
    statuses.mockReset()
    statuses.mockResolvedValue(STATUSES)
    create.mockReset()
    attach.mockReset()
  })

  it('글이 먼저 만들어지고 파일은 하나씩 붙는다', async () => {
    create.mockResolvedValue({ id: 'voc-9' })
    attach.mockResolvedValue({})
    await show([])
    await userEvent.click(screen.getByRole('button', { name: '의견 등록' }))
    await userEvent.type(screen.getByLabelText('제목'), '캡처 있음')
    await userEvent.type(screen.getByLabelText('내용'), '이렇게 나옵니다')
    const one = new File(['a'], 'a.png', { type: 'image/png' })
    const two = new File(['bb'], 'b.log', { type: 'text/plain' })
    await userEvent.upload(screen.getByLabelText('첨부'), [one, two])
    expect(screen.getByText('a.png')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '등록' }))
    await waitFor(() => expect(attach).toHaveBeenCalledTimes(2))
    expect(create).toHaveBeenCalledTimes(1)
    expect(attach.mock.calls[0][0]).toBe('voc-9')
    expect((attach.mock.calls[0][1] as File).name).toBe('a.png')
  })
})
