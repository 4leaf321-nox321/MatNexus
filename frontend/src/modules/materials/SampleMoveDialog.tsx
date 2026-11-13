/**
 * 고른 **시료째** 다른 재료로 옮기는 창(2026-11-14, VOC 59).
 *
 * 두께로 받을 재료를 계산하는 길(「다른 두께로 옮기기」)은 같은 부서 · 같은 Grade · Details 안에서만
 * 찾았다. 여기서는 받을 재료를 사람이 고른다 — 분류(Family · Category · Grade)가 같아야 하고, 받는
 * 재료 · 시료 · 시편을 고칠 수 있어야 한다(서버가 판정하고 까닭을 말한다). 시료를 쪼개지 않는다 —
 * 쪼개면 측정 의뢰 연결이 어긋난다. T-번호 · 처리 결과 · 채택은 그대로 따라가고 이름은 받은 재료
 * 기준으로 다시 계산된다.
 */

import { useEffect, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { Material, RelocatePlan, RelocateResult } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { RelocateCards } from '@/modules/materials/RelocateCards'
import type { CardAction } from '@/modules/materials/RelocateCards'
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

export function SampleMoveDialog({
  open,
  sampleId,
  sampleName,
  onClose,
  onDone,
}: {
  open: boolean
  sampleId: string
  sampleName: string
  onClose: () => void
  onDone: (result: RelocateResult) => void
}) {
  const [target, setTarget] = useState<Material | null>(null)
  const [plan, setPlan] = useState<RelocatePlan | null>(null)
  const [actions, setActions] = useState<Record<string, CardAction>>({})
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 열 때마다 새로 — 지난번에 고른 재료가 남으면 다른 시료에 그대로 걸린다.
  useEffect(() => {
    if (!open) return
    setTarget(null)
    setPlan(null)
    setActions({})
    setComment('')
    setError(null)
  }, [open])

  // **고르면 서버에 묻는다** — 무엇이 막히는지 · 어느 카드가 걸리는지는 서버가 안다.
  useEffect(() => {
    if (!open || !target) return
    let cancelled = false
    setError(null)
    materialsApi
      .movePlan({ sample_ids: [sampleId], target_material_id: target.id, card_actions: {} })
      .then((found) => {
        if (!cancelled) setPlan(found)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setPlan(null)
          setError(caught instanceof Error ? caught : new Error('계획을 받지 못했습니다.'))
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, target, sampleId])

  async function submit() {
    if (!plan || !target) return
    setBusy(true)
    setError(null)
    try {
      const done = await materialsApi.move({
        sample_ids: [sampleId],
        target_material_id: target.id,
        card_actions: Object.fromEntries(
          Object.entries(actions).filter(([, action]) => action === 'deprecate')
        ),
        comment: comment.trim() || null,
      })
      onDone(done)
      onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('옮기지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>다른 재료로 옮기기</DialogTitle>
          <DialogDescription>
            시료 <b>{sampleName}</b> 를 <b>시료째</b> 고른 재료로 옮깁니다. 분류(Family ·
            Category · Grade)가 같은 재료만 받을 수 있고, 시험 · 처리 결과 · 채택은 그대로
            따라갑니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <MaterialPicker
            value={target}
            onSelect={setTarget}
            placeholder="받을 재료 선택"
            ariaLabel="받을 재료"
          />

          <ErrorNotice error={error} />

          {plan && (
            <div className="space-y-3">
              <p>
                옮길 것: <b>시편 {plan.specimens}개</b> · 시험 {plan.test_runs}건
              </p>
              {plan.targets.map((one) => (
                <p key={one.from_material_id} className="font-mono text-xs">
                  {one.from_material_name} → <b>{one.to_material_name}</b>
                </p>
              ))}
              {plan.records.length > 0 && (
                <p className="text-muted-foreground text-xs">
                  이 시험을 쓴 기록 {plan.records.length}개는 원 재료에 그때 계산한 기록으로
                  남습니다.
                </p>
              )}
              {plan.blocked.length > 0 && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
                  <p className="font-medium">못 옮기는 까닭</p>
                  <ul className="mt-1 space-y-0.5">
                    {plan.blocked.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
              )}
              <RelocateCards
                cards={plan.cards}
                actions={actions}
                onAction={(id, action) => setActions((now) => ({ ...now, [id]: action }))}
                comment={comment}
                onComment={setComment}
                commentId="sample-move-comment"
                placeholder="예: 재료를 잘못 골라 등록 — 바른 재료로 옮김"
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button onClick={() => void submit()} disabled={!plan || plan.specimens === 0 || busy}>
            {busy ? '옮기는 중…' : '시료째 옮기기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
