/**
 * VOC — 앱 안의 제보 창구.
 *
 * 폐쇄망에서는 GitHub 가 창구가 될 수 없다. 여기가 없으면 문제는 구두로만 오가고
 * 기록이 남지 않는다.
 *
 * 접수할 때 **직전에 보던 화면 경로**를 함께 담는다 — "그 화면에서 안 돼요" 를
 * 재현하는 실마리다.
 */

import { useEffect, useState } from 'react'
import { MessageSquarePlus, Pencil, Trash2 } from 'lucide-react'

import { vocApi } from '@/modules/voc/api'
import type { VocItem } from '@/modules/voc/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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

const STATUS_LABELS: Record<string, string> = {
  open: '접수',
  in_progress: '확인 중',
  resolved: '처리됨',
}

export default function VocPage() {
  const { user } = useAuth()
  const items = useResource(() => vocApi.list(), [])
  const [writing, setWriting] = useState(false)
  const [replying, setReplying] = useState<VocItem | null>(null)
  const [editing, setEditing] = useState<VocItem | null>(null)
  const [deleting, setDeleting] = useState<VocItem | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  /**
   * 고치거나 지울 수 있는가. **서버와 같은 규칙이다**(`voc/routes.py` 의 `_mine`).
   *
   * 낸 사람은 답변 전까지, 관리자는 언제나. 답변이 달린 뒤에 본문이 바뀌면
   * 답변이 딴 소리가 된다 — 읽는 사람은 관리자가 엉뚱한 답을 한 것으로 본다.
   *
   * `is_mine` 은 서버가 준다. **이름으로 짐작하지 않는다** — 동명이인이면 남의
   * 것에 단추가 달리고, 눌러야 막힌다.
   */
  const mayChange = (item: VocItem) =>
    Boolean(user?.is_system_admin) || (item.is_mine && !item.reply)

  const rows = items.data ?? []

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="VOC"
        description="불편한 점이나 필요한 기능을 남겨 주세요."
        actions={
          <Button onClick={() => setWriting(true)}>
            <MessageSquarePlus className="size-4" />
            의견 남기기
          </Button>
        }
      />

      <ErrorNotice error={error ?? items.error} className="mb-4" />

      {!items.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          접수된 의견이 없습니다.
        </div>
      )}

      <ul className="space-y-3">
        {rows.map((item) => (
          <li key={item.id} className="rounded-md border p-4">
            <div className="mb-1 flex items-center gap-2">
              <h2 className="font-medium">{item.title}</h2>
              <Badge variant="outline">{STATUS_LABELS[item.status] ?? item.status}</Badge>

              {mayChange(item) && (
                <div className="ml-auto flex shrink-0 gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-7"
                    aria-label={`${item.title} 고치기`}
                    onClick={() => setEditing(item)}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-7"
                    aria-label={`${item.title} 삭제`}
                    onClick={() => setDeleting(item)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              )}
            </div>
            <p className="text-muted-foreground text-sm whitespace-pre-wrap">{item.body}</p>
            <p className="text-muted-foreground mt-2 text-xs">
              {item.created_by ?? '알 수 없음'} ·{' '}
              {new Date(item.created_at).toLocaleString('ko-KR')}
              {item.page_path && ` · ${item.page_path}`}
            </p>

            {item.reply && (
              <div className="bg-muted mt-3 rounded-md p-3 text-sm">
                <p className="mb-1 text-xs font-medium">답변</p>
                <p className="whitespace-pre-wrap">{item.reply}</p>
              </div>
            )}

            {user?.is_system_admin && !item.reply && (
              <Button
                size="sm"
                variant="outline"
                className="mt-3"
                onClick={() => setReplying(item)}
              >
                답변
              </Button>
            )}
          </li>
        ))}
      </ul>

      <WriteDialog
        open={writing}
        onClose={() => setWriting(false)}
        onDone={() => {
          setWriting(false)
          items.reload()
        }}
      />

      <ReplyDialog
        item={replying}
        onClose={() => setReplying(null)}
        onDone={() => {
          setReplying(null)
          items.reload()
        }}
      />

      <EditDialog
        item={editing}
        onClose={() => setEditing(null)}
        onDone={() => {
          setEditing(null)
          items.reload()
        }}
      />

      {/* **기록이 없어진다는 것을 말한다.** VOC 는 「문제가 구두로만 오가고
          기록이 남지 않는」 것을 막으려고 있는 창구다. */}
      <ConfirmDialog
        open={deleting !== null}
        title="접수 내역을 지웁니다"
        busy={busy}
        body={
          <>
            <b>{deleting?.title}</b> 이 사라집니다.
            <p className="text-muted-foreground mt-2">
              무슨 제보가 있었는지도 함께 없어집니다 — 답을 기다리는 중이면 지우는 대신
              그대로 두세요.
            </p>
          </>
        }
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return
          setBusy(true)
          setError(null)
          try {
            await vocApi.remove(deleting.id)
            setDeleting(null)
            items.reload()
          } catch (caught) {
            setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
          } finally {
            setBusy(false)
          }
        }}
      />
    </div>
  )
}

function WriteDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await vocApi.create({
        title,
        body,
        // 직전 화면을 담는다. 사용자가 따로 적지 않아도 재현 실마리가 남는다.
        page_path: document.referrer ? new URL(document.referrer).pathname : null,
      })
      setTitle('')
      setBody('')
      onDone()
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
          <DialogDescription>관리자가 확인하고 답변합니다.</DialogDescription>
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
            접수
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 낸 것을 고친다. **제목과 본문만이다** — 상태는 관리자가 답변으로 정하고,
 * 화면 경로는 접수 당시의 사실이라 나중에 고칠 것이 아니다.
 */
function EditDialog({
  item,
  onClose,
  onDone,
}: {
  item: VocItem | null
  onClose: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 열릴 때마다 그 건의 값으로 되돌린다 — 하나를 고치다 닫고 다른 것을 열었을
  // 때 앞엣것의 글이 남아 있으면, 그대로 저장하는 순간 덮인다.
  useEffect(() => {
    if (!item) return
    setTitle(item.title)
    setBody(item.body)
    setError(null)
  }, [item])

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
          <DialogTitle>의견 고치기</DialogTitle>
          <DialogDescription>답변이 달리면 더는 고칠 수 없습니다.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="voc-edit-title">제목</Label>
            <Input
              id="voc-edit-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="voc-edit-body">내용</Label>
            <textarea
              id="voc-edit-body"
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
          <Button disabled={busy || !title || !body} onClick={() => void submit()}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReplyDialog({
  item,
  onClose,
  onDone,
}: {
  item: VocItem | null
  onClose: () => void
  onDone: () => void
}) {
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    if (!item) return
    setBusy(true)
    setError(null)
    try {
      await vocApi.reply(item.id, reply, 'resolved')
      setReply('')
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('답변에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>답변</DialogTitle>
          <DialogDescription>{item?.title}</DialogDescription>
        </DialogHeader>

        <textarea
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          rows={5}
          className="border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
        />

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !reply} onClick={submit}>
            답변 등록
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
