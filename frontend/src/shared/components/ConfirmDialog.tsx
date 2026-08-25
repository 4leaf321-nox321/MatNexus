/**
 * 되돌릴 수 없는 일을 하기 전에 **한 번 묻는다.**
 *
 * 실사용에서 나왔다 — *"시험 데이터 삭제 시 물어보는 거 없이 그냥 삭제하니까
 * 위험해."* 실제로 이 저장소의 삭제는 전부 누르는 즉시 돌았다(시험·재료·시편).
 *
 * ## 무엇을 지우는지 이름으로 말한다
 *
 * "정말 삭제하시겠습니까?" 만으로는 **무엇을** 지우는지 안 보인다. 목록에서
 * 옆줄을 눌렀을 수도 있고, 여러 개를 골랐다면 몇 개인지가 판단의 전부다.
 *
 * ## 되돌릴 수 있는지 말한다
 *
 * 시험 데이터는 원본 파일과 처리 결과가 함께 걸려 있다. "지워집니다" 와
 * "복구할 수 없습니다" 는 사람에게 다른 무게다.
 *
 * ## 기본 초점은 취소다
 *
 * 엔터를 누르는 손이 그대로 이어지는 자리라, 확인이 기본이면 묻는 뜻이 없다.
 */

import { useEffect, useRef } from 'react'
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

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = '삭제',
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  /** 무엇이 사라지는지. **이름과 수를 여기 적는다.** */
  body: ReactNode
  confirmLabel?: string
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const cancel = useRef<HTMLButtonElement>(null)

  // **초점을 취소에 둔다.** 목록에서 엔터로 넘어온 손이 그대로 확인을 누르면
  // 묻는 뜻이 없다.
  useEffect(() => {
    if (open) cancel.current?.focus()
  }, [open])

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>되돌릴 수 없습니다.</DialogDescription>
        </DialogHeader>

        <div className="text-sm">{body}</div>

        <DialogFooter>
          <Button ref={cancel} variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? '지우는 중…' : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
