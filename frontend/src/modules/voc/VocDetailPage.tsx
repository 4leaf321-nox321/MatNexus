/**
 * VOC 한 건 — **본문·이력·옮기기.**
 *
 * 목록(`VocPage`)은 여는 자리고, 절차는 여기서 돈다. 등록부터 지금까지 누가 언제
 * 무슨 말로 상태를 옮겼는지가 시간순으로 흐르고, 아래에 **이 사람이 지금 갈 수
 * 있는 곳**만 단추로 선다.
 *
 * ## 화면이 규칙을 외우지 않는다
 *
 * 어느 상태에서 어디로 갈 수 있는지, 그때 말이 필요한지는 서버가 `allowed` ·
 * `note_required` 로 준다. 여기 적어 두면 서버와 어긋나는 날이 오고, 그날 단추는
 * 눌리는데 422 가 난다.
 */

import { useState } from 'react'
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { StatusBadge } from '@/modules/voc/VocPage'
import { STATUS_TONES, vocApi } from '@/modules/voc/api'
import type { VocDetail, VocEvent } from '@/modules/voc/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Stamp } from '@/shared/components/Stamp'
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
import { useResource } from '@/shared/hooks/useResource'

const TEXTAREA =
  'border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none'

export default function VocDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const item = useResource(() => vocApi.get(id), [id])
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [removingEvent, setRemovingEvent] = useState<VocEvent | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const detail = item.data

  return (
    <div className="mx-auto max-w-4xl">
      <Link
        to="/voc"
        className="text-muted-foreground hover:text-foreground mb-3 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        VOC 목록
      </Link>

      <ErrorNotice error={item.error ?? error} className="mb-4" />

      {detail && (
        <>
          <header className="mb-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground tabular-nums">#{detail.seq}</span>
              <h1 className="text-xl font-semibold">{detail.title}</h1>
              <StatusBadge item={detail} />
              {detail.can_edit && (
                <div className="ml-auto flex shrink-0 gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="편집"
                    onClick={() => setEditing(true)}
                  >
                    <Pencil className="size-3.5" />
                    편집
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="삭제"
                    onClick={() => setDeleting(true)}
                  >
                    <Trash2 className="size-3.5" />
                    삭제
                  </Button>
                </div>
              )}
            </div>
            <p className="text-muted-foreground mt-1 text-sm">
              {detail.created_by ?? '알 수 없음'} · <Stamp at={detail.created_at} />
              {detail.page_path && (
                <>
                  {' '}
                  · 보던 화면 <code className="font-mono">{detail.page_path}</code>
                </>
              )}
            </p>
          </header>

          <section className="mb-6 rounded-md border p-4">
            <p className="whitespace-pre-wrap">{detail.body}</p>
          </section>

          <section className="mb-6">
            <h2 className="mb-2 font-medium">이력</h2>
            <Timeline
              events={detail.events}
              onRemove={detail.can_delete_events ? setRemovingEvent : undefined}
            />
          </section>

          <ActionBox
            detail={detail}
            onDone={() => {
              setError(null)
              item.reload()
            }}
          />

          <EditDialog
            item={editing ? detail : null}
            onClose={() => setEditing(false)}
            onDone={() => {
              setEditing(false)
              item.reload()
            }}
          />

          {/* **잘못 옮긴 줄을 지운다** — 관리자만. 「해결」 로 갔다가 「처리 중」 으로
              되돌린 실수가 이력에 남아 있었다(VOC 2026-09-13). 지우면 상태는 남은
              이력의 마지막 이동으로 돌아간다. */}
          <ConfirmDialog
            open={removingEvent !== null}
            title="이력 한 줄을 지웁니다"
            busy={busy}
            body={
              removingEvent ? (
                <>
                  <b>
                    {removingEvent.from_status !== removingEvent.to_status
                      ? `${removingEvent.to_status_label} 로 옮김`
                      : '댓글'}
                  </b>
                  {removingEvent.note && <> — {removingEvent.note}</>}
                  <p className="text-muted-foreground mt-2">
                    상태를 옮긴 줄이면 이 건의 상태는 남은 이력의 마지막 이동으로 돌아갑니다.
                  </p>
                </>
              ) : null
            }
            onClose={() => setRemovingEvent(null)}
            onConfirm={async () => {
              if (!removingEvent) return
              setBusy(true)
              setError(null)
              try {
                await vocApi.removeEvent(detail.id, removingEvent.id)
                setRemovingEvent(null)
                item.reload()
              } catch (caught) {
                setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
              } finally {
                setBusy(false)
              }
            }}
          />

          {/* **기록이 없어진다는 것을 말한다.** VOC 는 「문제가 구두로만 오가고
              기록이 남지 않는」 것을 막으려고 있는 창구다. 이력도 함께 간다. */}
          <ConfirmDialog
            open={deleting}
            title="접수 내역을 지웁니다"
            busy={busy}
            body={
              <>
                <b>#{detail.seq} {detail.title}</b> 이 이력 {detail.events.length}건과 함께
                사라집니다.
                <p className="text-muted-foreground mt-2">
                  무슨 제보가 있었는지도 함께 없어집니다 — 처리가 끝난 건이면 지우는 대신
                  종료로 두세요.
                </p>
              </>
            }
            onClose={() => setDeleting(false)}
            onConfirm={async () => {
              setBusy(true)
              setError(null)
              try {
                await vocApi.remove(detail.id)
                navigate('/voc')
              } catch (caught) {
                setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
              } finally {
                setBusy(false)
              }
            }}
          />
        </>
      )}
    </div>
  )
}

/**
 * 이력 — 등록·상태 변경·댓글이 시간순으로. **상태가 바뀐 줄이 눈에 띈다** —
 * 댓글 사이에서 「언제 해결로 갔나」 를 찾는 것이 이 목록의 용도다.
 */
function Timeline({
  events,
  onRemove,
}: {
  events: VocEvent[]
  /** 있으면 줄마다 삭제 단추가 선다 — 서버가 `can_delete_events` 로 정한다. 등록 줄은 못 지운다. */
  onRemove?: (event: VocEvent) => void
}) {
  return (
    <ol className="space-y-2" aria-label="이력">
      {events.map((one) => {
        const moved = one.from_status !== one.to_status
        const registered = one.from_status === null
        return (
          <li key={one.id} className="flex gap-3 rounded-md border p-3">
            <div className="text-muted-foreground w-36 shrink-0">
              <Stamp at={one.at} />
              <p className="mt-0.5 truncate">{one.by ?? '알 수 없음'}</p>
            </div>
            <div className="min-w-0 flex-1">
              {registered ? (
                <Badge variant="outline" className={STATUS_TONES[one.to_status] ?? ''}>
                  등록
                </Badge>
              ) : moved ? (
                <Badge variant="outline" className={STATUS_TONES[one.to_status] ?? ''}>
                  {one.to_status_label} 로 옮김
                </Badge>
              ) : (
                <Badge variant="secondary">댓글</Badge>
              )}
              {one.note && <p className="mt-1.5 whitespace-pre-wrap">{one.note}</p>}
            </div>
            {onRemove && !registered && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8 shrink-0"
                aria-label="이력 삭제"
                title="이 줄을 지웁니다 — 잘못 옮긴 상태를 되돌릴 때"
                onClick={() => onRemove(one)}
              >
                <Trash2 className="size-4" />
              </Button>
            )}
          </li>
        )
      })}
    </ol>
  )
}

/**
 * 옮기거나 말을 보탠다. 단추는 서버가 말한 것만 선다.
 *
 * **말이 필요한 곳은 말 없이는 안 눌린다.** 「해결」 만 찍힌 건은 무엇이 바뀌었는지
 * 아무도 모르고, 이유 없는 「반려」 는 낸 사람이 다시 낼 수밖에 없다.
 */
function ActionBox({ detail, onDone }: { detail: VocDetail; onDone: () => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const trimmed = note.trim()

  async function send(status: string | null) {
    setBusy(true)
    setError(null)
    try {
      await vocApi.event(detail.id, { status, note: trimmed || null })
      setNote('')
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('보내지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-md border p-4">
      <Label htmlFor="voc-note" className="mb-1.5 block">
        댓글 등록
      </Label>
      <textarea
        id="voc-note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={3}
        className={TEXTAREA}
        placeholder={
          detail.allowed.length > 0
            ? '무엇을 했는지, 왜인지 — 상태를 옮길 때 함께 남습니다.'
            : '덧붙일 말을 남깁니다. 상태는 관리자와 낸 사람이 옮깁니다.'
        }
      />
      <ErrorNotice error={error} className="mt-2" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {detail.allowed.map((status) => {
          const needs = detail.note_required.includes(status)
          return (
            <Button
              key={status}
              size="sm"
              variant={status === 'resolved' || status === 'closed' ? 'default' : 'outline'}
              disabled={busy || (needs && !trimmed)}
              title={needs && !trimmed ? '말을 적어야 옮길 수 있습니다' : undefined}
              onClick={() => send(status)}
            >
              {detail.allowed_labels[status] ?? status}
            </Button>
          )
        })}
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          disabled={busy || !trimmed}
          onClick={() => send(null)}
        >
          말만 남기기
        </Button>
      </div>
    </section>
  )
}

/**
 * 낸 것을 고친다. **제목과 본문만이다** — 상태는 절차가 정하고, 화면 경로는 접수
 * 당시의 사실이라 나중에 고칠 것이 아니다.
 */
function EditDialog({
  item,
  onClose,
  onDone,
}: {
  item: VocDetail | null
  onClose: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [opened, setOpened] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 열릴 때 지금 값을 채운다. 렌더마다 채우면 치는 글자가 되돌아간다.
  if (item && opened !== item.id) {
    setOpened(item.id)
    setTitle(item.title)
    setBody(item.body)
  }
  if (!item && opened !== null) setOpened(null)

  async function submit() {
    if (!item) return
    setBusy(true)
    setError(null)
    try {
      await vocApi.update(item.id, { title, body })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('고치지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>편집</DialogTitle>
          <DialogDescription>남이 말을 남기기 전까지만 고칠 수 있습니다.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="voc-edit-title">제목</Label>
            <Input
              id="voc-edit-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="voc-edit-body">내용</Label>
            <textarea
              id="voc-edit-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={6}
              className={TEXTAREA}
            />
          </div>
        </div>
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !title || !body} onClick={submit}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
