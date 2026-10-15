/**
 * 자료 관리자에게 **부탁한다** — 카드 확정 요청 · 선언 값 승인 요청(2026-10-15).
 *
 * 확정 · 승인은 자료 관리자만 한다(ADR 0035). 전에는 부탁할 길이 없어서 만든 사람은 누구에게
 * 말해야 할지 몰랐고, 자료 관리자는 홈의 숫자나 「승인 대기 값」 화면을 열어야 알았다.
 *
 * **보낸 결과를 창 안에서 말한다.** 이 앱에는 토스트가 없다 — 창이 그냥 닫히면 「갔나?」 를
 * 알 길이 없고, 받을 사람이 0명이면(자료 관리자가 없거나 자기 혼자면) 그 사실이 묻힌다.
 */

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Textarea } from '@/shared/components/ui/textarea'

/** 받은 사람 수를 말로 — 0 이면 부탁이 아무에게도 안 갔다는 것을 숨기지 않는다. */
export function askedMessage(notified: number): string {
  return notified > 0
    ? `자료 관리자 ${notified}명에게 알렸습니다.`
    : '알릴 자료 관리자가 없습니다 — 시스템 관리자에게 자료 관리자 지정을 부탁하세요.'
}

export function AskDialog({
  open,
  title,
  body,
  onSend,
  onClose,
}: {
  open: boolean
  title: string
  /** 무엇을 부탁하는지 — 카드 이름 · 기다리는 값 수. */
  body: ReactNode
  /** 보내고 **결과를 말로** 돌려준다. 실패는 던진다 — 창 안에 적는다. */
  onSend: (note: string | undefined) => Promise<string>
  onClose: () => void
}) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 다시 열면 새 부탁이다 — 지난번 말과 결과를 들고 있지 않는다.
  useEffect(() => {
    if (open) {
      setNote('')
      setSent(null)
      setError(null)
    }
  }, [open])

  async function send() {
    setBusy(true)
    setError(null)
    try {
      setSent(await onSend(note.trim() || undefined))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '요청을 보내지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            자료 관리자에게 알림이 갑니다. 상태는 바뀌지 않습니다 — 확정 · 승인은 자료 관리자가
            합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 text-sm">
          <div>{body}</div>
          {sent === null ? (
            <Textarea
              aria-label="남길 말"
              placeholder="남길 말 (선택) — 어디에 쓸 값인지, 언제까지 필요한지"
              maxLength={500}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={busy}
            />
          ) : (
            <p role="status" className="font-medium">
              {sent}
            </p>
          )}
          {error && (
            <p role="alert" className="text-destructive">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          {sent === null ? (
            <>
              <Button variant="ghost" onClick={onClose} disabled={busy}>
                취소
              </Button>
              <Button onClick={() => void send()} disabled={busy}>
                {busy ? '보내는 중…' : '요청 보내기'}
              </Button>
            </>
          ) : (
            <Button onClick={onClose}>닫기</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
