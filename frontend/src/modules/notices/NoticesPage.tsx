/**
 * 공지 — 읽기는 모두, 쓰기는 시스템 관리자.
 *
 * 폐쇄망에서 **배포 없이 안내를 갱신하는 유일한 수단**이다. 그래서 관리자가
 * 이 화면에서 바로 쓰고 발행할 수 있어야 한다.
 */

import { useState } from 'react'
import { Megaphone, Plus } from 'lucide-react'

import { noticesApi } from '@/modules/notices/api'
import { useAuth } from '@/shared/auth/AuthContext'
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

      <ErrorNotice error={notices.error} className="mb-4" />

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
            </div>
            <p className="text-muted-foreground text-sm whitespace-pre-wrap">{notice.body}</p>
            <p className="text-muted-foreground mt-2 text-xs">
              {new Date(notice.published_at ?? notice.created_at).toLocaleString('ko-KR')}
            </p>
          </li>
        ))}
      </ul>

      <WriteDialog
        open={writing}
        onClose={() => setWriting(false)}
        onDone={() => {
          setWriting(false)
          notices.reload()
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
  const [isPopup, setIsPopup] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await noticesApi.create({ title, body, is_popup: isPopup, is_published: true })
      setTitle('')
      setBody('')
      setIsPopup(false)
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('작성에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>공지 작성</DialogTitle>
          <DialogDescription>발행하면 모든 사용자에게 보입니다.</DialogDescription>
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
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !title || !body} onClick={submit}>
            발행
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
