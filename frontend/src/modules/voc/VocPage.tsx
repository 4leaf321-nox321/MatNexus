/**
 * VOC — 앱 안의 제보 창구. **게시판이고 절차다.**
 *
 * 폐쇄망에서는 GitHub 가 창구가 될 수 없다. 여기가 없으면 문제는 구두로만 오가고
 * 기록이 남지 않는다.
 *
 * ## 카드 더미에서 게시판으로 (2026-09-11)
 *
 * 전에는 낸 사람과 관리자만 보는 카드가 한 건씩 쌓였고, 답변 한 줄이 절차의
 * 전부였다. 같은 문제를 여럿이 따로 내고, 무엇이 고쳐졌는지는 낸 사람만 알았다.
 * 이제 **로그인한 사람은 다 보고**, 한 건은 번호를 달고 「등록 → 접수 → 처리 중 →
 * 해결 → 종료」 를 거친다. 목록은 그 흐름을 한눈에 보이는 표다 — 누가 언제 냈고,
 * 지금 어디까지 갔고, 마지막으로 누가 손댔나.
 *
 * 상세(`/voc/:id`)에서 본문·이력·옮기기를 한다. 목록은 여는 자리다.
 *
 * 접수할 때 **직전에 보던 화면 경로**를 함께 담는다 — "그 화면에서 안 돼요" 를
 * 재현하는 실마리다.
 */

import { useState } from 'react'
import { MessageSquare, MessageSquarePlus, Search } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { STATUS_TONES, vocApi } from '@/modules/voc/api'
import type { VocItem } from '@/modules/voc/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Stamp } from '@/shared/components/Stamp'
import { SubTabs } from '@/shared/components/SubTabs'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { ROW_FOCUS_STYLE, useRowFocus } from '@/shared/hooks/useRowFocus'

const PAGE = 50

/** 상태 배지. 이름은 서버가 준 것, 색만 여기서. */
export function StatusBadge({ item }: { item: Pick<VocItem, 'status' | 'status_label'> }) {
  return (
    <Badge variant="outline" className={STATUS_TONES[item.status] ?? ''}>
      {item.status_label}
    </Badge>
  )
}

export default function VocPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<string>('')
  const [mine, setMine] = useState(false)
  // 치는 글자와 적용된 글자를 가른다 — 한 글자마다 목록을 다시 부르지 않는다.
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [writing, setWriting] = useState(false)

  const statuses = useResource(() => vocApi.statuses(), [])
  const page = useResource(
    () => vocApi.list({ status: status || undefined, q: q || undefined, mine, limit: PAGE, offset }),
    [status, q, mine, offset]
  )
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  const focus = useRowFocus(rows.map((one) => one.id))

  function narrow(next: { status?: string; mine?: boolean; q?: string }) {
    setOffset(0)
    if (next.status !== undefined) setStatus(next.status)
    if (next.mine !== undefined) setMine(next.mine)
    if (next.q !== undefined) setQ(next.q)
  }

  return (
    // 표라 폭을 스스로 좁히지 않는다 — 좁히면 표가 접힌다(`boundaries.test`).
    // 읽는 화면인 상세(`VocDetailPage`)만 좁힌다.
    <div>
      {/* **공지와 VOC 는 한 진입점이다.** 메뉴에 둘로 서 있으면 「어느 쪽에
          쓰지」 를 매번 묻는다 — 위에서 내려오는 글과 아래에서 올라가는 글일
          뿐, 사람에게는 같은 게시판이다. */}
      <SubTabs
        items={[
          { to: '/notices', label: '공지' },
          { to: '/voc', label: 'VOC' },
        ]}
      />
      <PageHeader
        title="VOC"
        description="불편한 점이나 필요한 기능을 남겨 주세요. 등록 → 접수 → 처리 중 → 해결 → 종료 로 흐르고, 누가 언제 옮겼는지 남습니다."
        actions={
          <Button onClick={() => setWriting(true)}>
            <MessageSquarePlus className="size-4" />
            의견 남기기
          </Button>
        }
      />

      <ErrorNotice error={page.error ?? statuses.error} className="mb-4" />

      {/* **상태로 거른다.** 「내가 낸 것 중 아직 안 된 것」 이 가장 흔한 물음이다. */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="상태로 거르기">
          <Chip active={status === ''} onClick={() => narrow({ status: '' })}>
            전체
          </Chip>
          {(statuses.data ?? []).map((one) => (
            <Chip
              key={one.key}
              active={status === one.key}
              onClick={() => narrow({ status: one.key })}
            >
              {one.label}
            </Chip>
          ))}
        </div>
        <label className="ml-1 flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={mine}
            onChange={(event) => narrow({ mine: event.target.checked })}
          />
          내가 낸 것만
        </label>
        <form
          className="relative ml-auto w-full sm:w-64"
          onSubmit={(event) => {
            event.preventDefault()
            narrow({ q: typed.trim() })
          }}
        >
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder="제목·내용으로 찾기"
            aria-label="VOC 찾기"
            className="pl-8"
          />
        </form>
      </div>

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          {status || q || mine ? '거른 조건에 맞는 것이 없습니다.' : '접수된 의견이 없습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16 text-right">번호</TableHead>
                <TableHead>제목</TableHead>
                <TableHead className="w-24">상태</TableHead>
                <TableHead className="w-28">올린 사람</TableHead>
                <TableHead className="w-36">올린 날짜</TableHead>
                <TableHead className="w-48">최근 처리</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <TableRow
                  key={item.id}
                  className={`cursor-pointer ${ROW_FOCUS_STYLE}`}
                  {...focus.rowProps(item.id)}
                  // 줄 어디를 눌러도 연다. 키보드는 제목 링크가 받는다(Enter →
                  // 줄 안의 첫 링크, `useRowFocus`).
                  onClick={() => navigate(`/voc/${item.id}`)}
                >
                  <TableCell className="text-right tabular-nums">{item.seq}</TableCell>
                  <TableCell>
                    <Link
                      to={`/voc/${item.id}`}
                      className="font-medium hover:underline"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {item.title}
                    </Link>
                    {/* **말이 오간 건을 보인다.** 등록만 있는 것과 오가는 중인 것이
                        같아 보이면 어느 쪽부터 볼지 모른다. */}
                    {item.event_count > 0 && (
                      <span className="text-muted-foreground ml-2 inline-flex items-center gap-0.5">
                        <MessageSquare className="size-3" aria-hidden />
                        <span className="tabular-nums">{item.event_count}</span>
                      </span>
                    )}
                    {item.is_mine && (
                      <Badge variant="secondary" className="ml-2">
                        내 것
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge item={item} />
                  </TableCell>
                  <TableCell>{item.created_by ?? '알 수 없음'}</TableCell>
                  <TableCell>
                    <Stamp at={item.created_at} />
                  </TableCell>
                  <TableCell>
                    {/* 등록만 된 건은 「최근 처리」 가 등록 그 자체다 — 비운다. */}
                    {item.status === 'open' && item.event_count === 0 ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <>
                        {item.status_by ?? '알 수 없음'} · <Stamp at={item.status_at} />
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {total > PAGE && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span className="text-muted-foreground tabular-nums">
            {offset + 1}–{Math.min(offset + PAGE, total)} / {total}건
          </span>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              이전
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              다음
            </Button>
          </div>
        </div>
      )}

      <WriteDialog
        open={writing}
        onClose={() => setWriting(false)}
        onDone={(id) => {
          setWriting(false)
          navigate(`/voc/${id}`)
        }}
      />
    </div>
  )
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-0.5 text-sm transition ${
        active ? 'border-primary bg-primary/10 text-foreground' : 'hover:bg-muted'
      }`}
    >
      {children}
    </button>
  )
}

function WriteDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: (id: string) => void
}) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const made = await vocApi.create({
        title,
        body,
        // 직전 화면을 담는다. 사용자가 따로 적지 않아도 재현 실마리가 남는다.
        page_path: document.referrer ? new URL(document.referrer).pathname : null,
      })
      setTitle('')
      setBody('')
      onDone(made.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('접수에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>의견 남기기</DialogTitle>
          <DialogDescription>
            등록되면 번호가 붙고, 관리자가 접수해 처리합니다. 진행은 그 건의 이력에 남습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="voc-title">제목</Label>
            <Input id="voc-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="voc-body">내용</Label>
            <textarea
              id="voc-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              className="border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
            />
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !title || !body} onClick={submit}>
            등록
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
