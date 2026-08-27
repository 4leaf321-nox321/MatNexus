/**
 * 공지 — 읽기는 모두, 쓰기는 시스템 관리자.
 *
 * 폐쇄망에서 **배포 없이 안내를 갱신하는 유일한 수단**이다. 그래서 관리자가
 * 이 화면에서 바로 쓰고 발행할 수 있어야 한다.
 */

import { useEffect, useState } from 'react'
import { Megaphone, Pencil, Plus, Trash2 } from 'lucide-react'

import { noticesApi } from '@/modules/notices/api'
import type { Notice } from '@/modules/notices/api'
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

export default function NoticesPage() {
  const { user } = useAuth()
  const notices = useResource(() => noticesApi.list(), [])
  const [writing, setWriting] = useState(false)
  /** 고치는 중인 공지. `null` 이면 새로 쓰는 것이다. */
  const [editing, setEditing] = useState<Notice | null>(null)
  const [deleting, setDeleting] = useState<Notice | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const rows = notices.data ?? []

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="공지"
        description="배포 없이 안내를 갱신할 수 있는 곳입니다."
        actions={
          user?.is_system_admin && (
            <Button onClick={() => setWriting(true)}>
              <Plus className="size-4" />
              공지 작성
            </Button>
          )
        }
      />

      <ErrorNotice error={error ?? notices.error} className="mb-4" />

      {!notices.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <Megaphone className="mx-auto mb-2 size-5 opacity-50" />
          공지가 없습니다.
        </div>
      )}

      <ul className="space-y-3">
        {rows.map((notice) => (
          <li key={notice.id} className="rounded-md border p-4">
            <div className="mb-1 flex items-center gap-2">
              <h2 className="font-medium">{notice.title}</h2>
              {!notice.is_published && (
                <Badge variant="outline" className="text-muted-foreground">
                  초안
                </Badge>
              )}
              {notice.is_popup && <Badge variant="outline">팝업</Badge>}

              {/* **오른쪽 끝에 붙인다.** 제목 옆에 두면 배지와 섞여, 읽으러 온
                  사람에게도 고치는 단추가 먼저 눈에 든다. */}
              {user?.is_system_admin && (
                <div className="ml-auto flex shrink-0 gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-7"
                    aria-label={`${notice.title} 고치기`}
                    onClick={() => setEditing(notice)}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-7"
                    aria-label={`${notice.title} 삭제`}
                    onClick={() => setDeleting(notice)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              )}
            </div>
            <p className="text-muted-foreground text-sm whitespace-pre-wrap">{notice.body}</p>
            <p className="text-muted-foreground mt-2 text-xs">
              {new Date(notice.published_at ?? notice.created_at).toLocaleString('ko-KR')}
            </p>
          </li>
        ))}
      </ul>

      <NoticeDialog
        open={writing || editing !== null}
        notice={editing}
        onClose={() => {
          setWriting(false)
          setEditing(null)
        }}
        onDone={() => {
          setWriting(false)
          setEditing(null)
          notices.reload()
        }}
      />

      {/* **「내리기」 를 함께 말한다.** 잘못 올린 것을 잠깐 감추는 것과 아예
          없애는 것은 다른 일인데, 사람은 그 자리에서 삭제부터 누른다. */}
      <ConfirmDialog
        open={deleting !== null}
        title="공지를 지웁니다"
        busy={busy}
        body={
          <>
            <b>{deleting?.title}</b> 과 그 읽음 기록이 사라집니다.
            <p className="text-muted-foreground mt-2">
              잠깐 감추려는 것이면 지우지 말고 <b>고치기에서 발행을 끄세요</b> — 내용과
              발행 시각이 남습니다.
            </p>
          </>
        }
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return
          setBusy(true)
          setError(null)
          try {
            await noticesApi.remove(deleting.id)
            setDeleting(null)
            notices.reload()
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

/**
 * 새로 쓰기와 고치기를 **한 창이 한다.**
 *
 * 둘로 나누면 칸이 두 벌이 되고, 「팝업으로 띄우기」 같은 칸을 하나에만 더하는
 * 날이 온다 — 그러면 고칠 때만 못 켜는 것이 생긴다.
 *
 * 고칠 때만 「발행」 을 보여 준다. 새로 쓰는 창에서는 단추가 곧 발행이라 칸이
 * 겹치고, **잘못 올린 것을 내리는 일**은 고치는 자리에서만 생긴다.
 */
function NoticeDialog({
  open,
  notice,
  onClose,
  onDone,
}: {
  open: boolean
  /** `null` 이면 새로 쓰는 것이다. */
  notice: Notice | null
  onClose: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [isPopup, setIsPopup] = useState(false)
  const [isPublished, setIsPublished] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // **열릴 때마다 그 공지의 값으로 되돌린다.** 안 그러면 하나를 고치다 닫고
  // 다른 것을 열었을 때 앞엣것의 글이 남아 있고, 그대로 저장하면 덮인다.
  useEffect(() => {
    if (!open) return
    setTitle(notice?.title ?? '')
    setBody(notice?.body ?? '')
    setIsPopup(notice?.is_popup ?? false)
    setIsPublished(notice?.is_published ?? true)
    setError(null)
  }, [open, notice])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      if (notice) {
        await noticesApi.update(notice.id, {
          title,
          body,
          is_popup: isPopup,
          is_published: isPublished,
        })
      } else {
        await noticesApi.create({ title, body, is_popup: isPopup, is_published: true })
      }
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{notice ? '공지 고치기' : '공지 작성'}</DialogTitle>
          <DialogDescription>
            {notice
              ? '이미 읽은 사람에게도 바뀐 내용이 보입니다.'
              : '발행하면 모든 사용자에게 보입니다.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="notice-title">제목</Label>
            <Input
              id="notice-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="notice-body">내용</Label>
            <textarea
              id="notice-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={6}
              className="border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isPopup}
              onChange={(event) => setIsPopup(event.target.checked)}
            />
            로그인 시 한 번 띄우기
          </label>
          {/* 전부 팝업이면 아무도 읽지 않는다. */}
          <p className="text-muted-foreground text-xs">중요한 공지에만 켜세요.</p>

          {/* **지우는 대신 내리는 길.** 발행을 끄면 남에게 안 보이고 내용과
              발행 시각은 남는다 — 다시 켜도 「언제 알려졌는가」 를 잃지 않는다. */}
          {notice && (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={isPublished}
                  onChange={(event) => setIsPublished(event.target.checked)}
                />
                발행
              </label>
              <p className="text-muted-foreground text-xs">
                끄면 초안으로 내려가 남에게 안 보입니다. 내용과 처음 발행한 시각은
                남습니다.
              </p>
            </>
          )}
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !title || !body} onClick={() => void submit()}>
            {notice ? '저장' : '발행'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
