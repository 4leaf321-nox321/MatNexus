/**
 * **물성 사용 보류** — 시험 상세의 안내와 자료 관리자용 걸기 · 풀기(2026-11-14, VOC 60).
 *
 * 문제가 의심되는 시험을 「쓰지 말라」 고 표시할 자리가 없었다. 메모에 적어도 채택 · 카드 · 통계는
 * 몰랐다. 걸리면 서버가 채택 · 카드를 막고 통계에서 뺀다 — 이 화면은 그 사실과 사유를 보이고,
 * 자료 관리자에게만 걸고 푸는 단추를 준다(등록자가 스스로 풀 수 있으면 보류가 뜻이 없다).
 */

import { Ban } from 'lucide-react'
import { useState } from 'react'

import { testsApi } from '@/modules/tests/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Textarea } from '@/shared/components/ui/textarea'

export function HoldPanel({
  runId,
  holdReason,
  heldBy,
  canSteward,
  onChanged,
}: {
  runId: string
  holdReason?: string | null
  heldBy?: string | null
  /** 자료 관리자(시스템 관리자 포함)인가 — 서버도 같은 판정으로 막는다. */
  canSteward: boolean
  onChanged: () => void
}) {
  const [writing, setWriting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setWriting(false)
      setReason('')
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (!holdReason && !canSteward) return null
  return (
    <div className="mb-6 space-y-2">
      {holdReason && (
        <div
          role="status"
          className="border-destructive/40 bg-destructive/5 rounded-md border p-3 text-sm"
        >
          <p className="text-destructive flex items-center gap-1.5 font-medium">
            <Ban className="size-4" />
            물성 사용 보류
            {heldBy && <span className="text-muted-foreground font-normal">· {heldBy}</span>}
          </p>
          <p className="mt-1 whitespace-pre-wrap">{holdReason}</p>
          <p className="text-muted-foreground mt-1 text-xs">
            이 시험은 채택 · 카드에 쓸 수 없고 통계 · 분석 · 글로벌 피팅에서 빠집니다. 이 시험을
            근거로 쓴 카드에는 비고가 붙었습니다.
          </p>
          {canSteward && (
            <Button
              size="sm"
              variant="outline"
              className="mt-2"
              disabled={busy}
              onClick={() => void run(() => testsApi.release(runId))}
            >
              보류 풀기
            </Button>
          )}
        </div>
      )}
      {!holdReason && canSteward && !writing && (
        <Button size="sm" variant="outline" onClick={() => setWriting(true)}>
          <Ban className="size-4" />
          물성 사용 보류
        </Button>
      )}
      {writing && (
        <div className="space-y-2 rounded-md border p-3">
          <label className="block text-sm font-medium" htmlFor="hold-reason">
            보류 사유
          </label>
          <Textarea
            id="hold-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="예: 시편 그립 미끄럼 의심 — 재시험 결과 확인 전까지 사용 보류"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={busy || !reason.trim()}
              onClick={() => void run(() => testsApi.hold(runId, reason.trim()))}
            >
              보류 걸기
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setWriting(false)}>
              취소
            </Button>
          </div>
        </div>
      )}
      <ErrorNotice error={error} />
    </div>
  )
}
