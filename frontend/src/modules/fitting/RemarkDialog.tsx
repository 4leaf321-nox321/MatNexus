/**
 * 카드에 **코멘트를 남긴다**(2026-10-16) — 확정하지 않는 사유 · 검토 의견 · 보완 요청.
 *
 * 카드에는 「반려」 상태가 없다(D8). 그래서 자료 관리자가 확정하지 않을 때 그 사유를 남길 자리가
 * 없었고, 확정을 부탁한 사람은 왜 초안으로 남아 있는지 몰랐다. 코멘트는 카드의 값 · 근거를
 * 바꾸지 않는다 — 말만 붙는다. 남기면 카드를 만든 사람과 확정을 부탁한 사람에게 알림이 간다.
 */

import { useEffect, useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { PropertyCard } from '@/modules/fitting/api'
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

export function RemarkDialog({
  card,
  onClose,
  onSaved,
}: {
  /** 코멘트를 달 카드. `null` 이면 닫혀 있다. */
  card: PropertyCard | null
  onClose: () => void
  onSaved: () => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 다른 카드로 열면 새 코멘트다 — 앞 카드에 쓰던 말을 들고 있지 않는다.
  useEffect(() => {
    setText('')
    setError(null)
  }, [card?.id])

  async function save() {
    if (!card || !text.trim()) return
    setBusy(true)
    setError(null)
    try {
      await fittingApi.addRemark(card.id, text.trim())
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '코멘트를 남기지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={card !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            「{card?.code} {card?.label}」 코멘트
          </DialogTitle>
          <DialogDescription>
            카드의 값은 바뀌지 않습니다. 카드를 만든 사람과 확정을 요청한 사람에게 알림이 갑니다.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          aria-label="코멘트"
          placeholder="확정하지 않는 사유 · 검토 의견 · 보완 요청"
          maxLength={1000}
          value={text}
          onChange={(event) => setText(event.target.value)}
          disabled={busy}
        />
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void save()} disabled={busy || !text.trim()}>
            {busy ? '남기는 중…' : '코멘트 남기기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
