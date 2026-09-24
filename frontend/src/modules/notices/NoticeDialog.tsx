/**
 * 새로 쓰기와 고치기를 **한 창이 한다.**
 *
 * 둘로 나누면 칸이 두 벌이 되고, 「팝업으로 띄우기」 같은 칸을 하나에만 더하는
 * 날이 온다 — 그러면 고칠 때만 못 켜는 것이 생긴다. 목록(쓰기)과 상세(고치기)가 이
 * 창 하나를 쓴다(게시판으로 나눈 2026-09-24 에 목록 파일에서 떼어 냈다).
 *
 * 고칠 때만 「발행」 을 보여 준다. 새로 쓰는 창에서는 단추가 곧 발행이라 칸이
 * 겹치고, **잘못 올린 것을 내리는 일**은 고치는 자리에서만 생긴다.
 */

import { useEffect, useState } from 'react'

import { noticesApi } from '@/modules/notices/api'
import type { Notice } from '@/modules/notices/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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

export function NoticeDialog({
  open,
  notice,
  onClose,
  onDone,
}: {
  open: boolean
  /** `null` 이면 새로 쓰는 것이다. */
  notice: Notice | null
  onClose: () => void
  onDone: (saved: Notice) => void
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
      const saved = notice
        ? await noticesApi.update(notice.id, {
            title,
            body,
            is_popup: isPopup,
            is_published: isPublished,
          })
        : await noticesApi.create({ title, body, is_popup: isPopup, is_published: true })
      onDone(saved)
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
          <DialogTitle>{notice ? '공지 편집' : '공지 작성'}</DialogTitle>
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
              rows={8}
              className="border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
            />
            <p className="text-muted-foreground text-xs">
              <code>**굵게**</code> 와 <code>`코드`</code> 는 그려서 보입니다. 줄바꿈은 적은 그대로입니다.
            </p>
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
