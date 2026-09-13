/**
 * 측정 의뢰 — **「이 시료의 이 물성을 재 달라」 가 기록으로 흐르는 게시판.**
 *
 * 플랫폼은 잰 뒤(시료 → 시편 → 시험 → 카드)부터만 있었다. 누가 무엇을 왜 재 달라고
 * 했고 어디까지 됐나는 메일과 구두에 있었다. 여기서 한 건은 번호를 달고 「접수 대기 →
 * 접수 → 시험 중 → 결과 전달 → 완료」 를 거치고, 항목에 시험이 붙어 결과가 채택되면
 * 진행률이 저절로 오른다.
 *
 * 탭은 **내가 낸 것 / 우리 부서가 받은 것 / 전체** — 어느 쪽인지는 서버가 `side` 로
 * 말한다. 상세(`/commissions/:id`)에서 항목·시험·이력·옮기기를 한다.
 */

import { useState } from 'react'
import { ClipboardPlus, MessageSquare, Search } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { STATUS_TONES, commissionsApi } from '@/modules/commissions/api'
import type { Commission, Scope } from '@/modules/commissions/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Stamp } from '@/shared/components/Stamp'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
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

const SCOPES: { key: Scope; label: string }[] = [
  { key: 'mine', label: '내가 낸 것' },
  { key: 'received', label: '우리 부서가 받은 것' },
  { key: 'all', label: '전체' },
]

/** 상태 배지. 이름은 서버가 준 것, 색만 여기서. */
export function StatusBadge({
  item,
}: {
  item: Pick<Commission, 'status' | 'status_label'>
}) {
  return (
    <Badge variant="outline" className={STATUS_TONES[item.status] ?? ''}>
      {item.status_label}
    </Badge>
  )
}

/** 진행률 — 채택된 결과 / 의뢰한 시편 수. 붙었지만 채택 전인 것은 괄호에. */
export function Progress({ progress }: { progress: Commission['progress'] }) {
  const pending = progress.linked - progress.done
  return (
    <span className="tabular-nums" title="채택된 결과 / 의뢰한 시편 수 (괄호: 붙었지만 채택 전)">
      {progress.done}/{progress.total}
      {pending > 0 && <span className="text-muted-foreground"> (+{pending})</span>}
    </span>
  )
}

export default function CommissionsPage() {
  const navigate = useNavigate()
  const [scope, setScope] = useState<Scope>('all')
  const [status, setStatus] = useState<string>('')
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)

  const statuses = useResource(() => commissionsApi.statuses(), [])
  const page = useResource(
    () =>
      commissionsApi.list({ scope, status: status || undefined, q: q || undefined, limit: PAGE, offset }),
    [scope, status, q, offset]
  )
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  const focus = useRowFocus(rows.map((one) => one.id))

  function narrow(next: { scope?: Scope; status?: string; q?: string }) {
    setOffset(0)
    if (next.scope !== undefined) setScope(next.scope)
    if (next.status !== undefined) setStatus(next.status)
    if (next.q !== undefined) setQ(next.q)
  }

  return (
    <div>
      <PageHeader
        title="측정 의뢰"
        description="시료의 물성을 측정 부서에 의뢰합니다. 접수 대기 → 접수 → 시험 중 → 결과 전달 → 완료 로 흐르고, 항목에 시험이 붙어 결과가 채택되면 진행률이 오릅니다."
        actions={
          <Button onClick={() => navigate('/commissions/new')}>
            <ClipboardPlus className="size-4" />새 의뢰
          </Button>
        }
      />

      <ErrorNotice error={page.error ?? statuses.error} className="mb-4" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="범위">
          {SCOPES.map((one) => (
            <Chip key={one.key} active={scope === one.key} onClick={() => narrow({ scope: one.key })}>
              {one.label}
            </Chip>
          ))}
        </div>
        <span className="text-muted-foreground mx-1">·</span>
        <div className="flex flex-wrap gap-1" role="group" aria-label="상태로 필터">
          <Chip active={status === ''} onClick={() => narrow({ status: '' })}>
            모든 상태
          </Chip>
          {(statuses.data ?? []).map((one) => (
            <Chip key={one.key} active={status === one.key} onClick={() => narrow({ status: one.key })}>
              {one.label}
            </Chip>
          ))}
        </div>
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
            placeholder="제목·목적으로 검색"
            aria-label="의뢰 검색"
            className="pl-8"
          />
        </form>
      </div>

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          {status || q || scope !== 'all' ? '거른 조건에 맞는 것이 없습니다.' : '측정 의뢰가 없습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16 text-right">번호</TableHead>
                <TableHead>제목</TableHead>
                <TableHead>시료</TableHead>
                <TableHead className="w-28">낸 부서</TableHead>
                <TableHead className="w-28">받는 부서</TableHead>
                <TableHead className="w-20 text-right">진행</TableHead>
                <TableHead className="w-24">상태</TableHead>
                <TableHead className="w-28">기한</TableHead>
                <TableHead className="w-48">최근 처리</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <TableRow
                  key={item.id}
                  className={`cursor-pointer ${ROW_FOCUS_STYLE}`}
                  {...focus.rowProps(item.id)}
                  onClick={() => navigate(`/commissions/${item.id}`)}
                >
                  <TableCell className="text-right tabular-nums">{item.seq}</TableCell>
                  <TableCell>
                    <Link
                      to={`/commissions/${item.id}`}
                      className="font-medium hover:underline"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {item.title}
                    </Link>
                    {item.priority === 'urgent' && (
                      <Badge variant="destructive" className="ml-2">
                        {item.priority_label}
                      </Badge>
                    )}
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
                    <span className="block">{item.sample.record_name}</span>
                    <span className="text-muted-foreground block">{item.sample.material_name}</span>
                  </TableCell>
                  <TableCell>{item.requester_workspace.name}</TableCell>
                  <TableCell>{item.lab_workspace.name}</TableCell>
                  <TableCell className="text-right">
                    <Progress progress={item.progress} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge item={item} />
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {item.due_on ?? <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    {item.status_by ?? '알 수 없음'} · <Stamp at={item.status_at} />
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
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              이전
            </Button>
            <Button size="sm" variant="outline" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
              다음
            </Button>
          </div>
        </div>
      )}
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
