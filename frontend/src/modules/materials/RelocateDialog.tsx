/**
 * 고른 시편을 **다른 두께의 같은 재료**로 옮기는 창(2026-09-29).
 *
 * 두께가 다른 재료에 잘못 넣은 시편을 바로잡는 길이다. 재료 수정으로 두께를 바꾸면 제대로
 * 들어간 시료까지 이름이 바뀌어 함께 옮겨진다 — 그래서 고른 시편만 옮긴다.
 *
 * ## 무엇이 어디로 가는지는 서버가 말한다
 *
 * 두께를 적으면 서버에 계획을 묻는다(`relocate-plan`, 아무것도 안 쓴다). 옮겨 갈 재료가
 * 이미 있는지, 시료가 통째로 가는지 일부만 가는지, 어느 카드가 걸리는지 — 화면이 짐작하면
 * 실제로 옮겨지는 것과 어긋난다.
 *
 * ## 카드 — 옮기는 것은 막지 않는다
 *
 * 옮기는 시험으로 만든 카드(확정 포함)에는 **코멘트가 반드시 붙는다.** 카드마다 정리(사용
 * 중지)를 고를 수 있고, 확정 카드의 정리는 자료 관리자만 한다(ADR 0035).
 *
 * 그 시험을 쓴 묶음·저장한 대표 곡선은 원 재료에 그때의 기록으로 남는다 — 알리기만 한다.
 */

import { useEffect, useState } from 'react'

import { LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { RelocatePlan, RelocateResult } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { Textarea } from '@/shared/components/ui/textarea'

const STATUS_LABEL: Record<string, string> = {
  published: '확정',
  draft: '초안',
  deprecated: '사용 중지',
}

type CardAction = 'note' | 'deprecate'

export function RelocateDialog({
  open,
  specimenIds,
  onClose,
  onDone,
}: {
  open: boolean
  specimenIds: string[]
  onClose: () => void
  onDone: (result: RelocateResult) => void
}) {
  const [thickness, setThickness] = useState('')
  const [plan, setPlan] = useState<RelocatePlan | null>(null)
  const [planning, setPlanning] = useState(false)
  const [actions, setActions] = useState<Record<string, CardAction>>({})
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 열 때마다 새로 — 지난번에 적은 두께가 남으면 다른 시편에 그대로 걸린다.
  useEffect(() => {
    if (!open) return
    setThickness('')
    setPlan(null)
    setActions({})
    setComment('')
    setError(null)
  }, [open])

  // **두께를 적으면 서버에 묻는다** — 타이핑마다가 아니라 멈췄을 때.
  const value = Number(thickness)
  const ready = thickness.trim() !== '' && Number.isFinite(value) && value > 0
  useEffect(() => {
    if (!open || !ready) {
      setPlan(null)
      return
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      setPlanning(true)
      setError(null)
      materialsApi
        .relocatePlan({
          specimen_ids: specimenIds,
          spec_thickness: value,
          spec_thickness_unit: LENGTH_UNIT,
          card_actions: {},
        })
        .then((found) => {
          if (!cancelled) setPlan(found)
        })
        .catch((caught: unknown) => {
          if (!cancelled) {
            setPlan(null)
            setError(caught instanceof Error ? caught : new Error('계획을 받지 못했습니다.'))
          }
        })
        .finally(() => {
          if (!cancelled) setPlanning(false)
        })
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, thickness, specimenIds.join(',')])

  async function submit() {
    if (!plan || !ready) return
    setBusy(true)
    setError(null)
    try {
      const done = await materialsApi.relocate({
        specimen_ids: specimenIds,
        spec_thickness: value,
        spec_thickness_unit: LENGTH_UNIT,
        // 고르지 않은 카드는 코멘트만 — 서버 기본과 같다. 고른 것만 싣는다.
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
          <DialogTitle>다른 두께로 옮기기</DialogTitle>
          <DialogDescription>
            고른 시편 {specimenIds.length}개를 <b>같은 재료의 다른 기준 두께</b>로 옮깁니다. 재료
            수정으로 두께를 바꾸면 제대로 들어간 시료까지 옮겨지므로, 고른 시편만 옮깁니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <div className="space-y-1">
            <Label htmlFor="relocate-thickness">기준 두께 ({LENGTH_UNIT})</Label>
            <Input
              id="relocate-thickness"
              type="number"
              step="any"
              min={0}
              className="h-8 w-40"
              value={thickness}
              onChange={(event) => setThickness(event.target.value)}
              placeholder="예: 1.2"
              autoFocus
            />
          </div>

          <ErrorNotice error={error} />
          {planning && !plan && <p className="text-muted-foreground">살펴보는 중…</p>}

          {plan && (
            <div className="space-y-3">
              <p>
                옮길 것: <b>시편 {plan.specimens}개</b> · 시험 {plan.test_runs}건
              </p>

              {plan.targets.map((target) => (
                <div key={target.from_material_id} className="rounded-md border px-3 py-2">
                  <p className="font-mono text-xs">
                    {target.from_material_name} → <b>{target.to_material_name}</b>
                  </p>
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    {target.exists
                      ? '이미 있는 재료입니다 — 그리로 합칩니다.'
                      : `없어서 새로 만듭니다 — ${target.from_material_name} 을 복사하고 두께만 바꿉니다(분류·용도·밀도·선언 물성 그대로).`}
                  </p>
                </div>
              ))}

              {plan.samples.length > 0 && (
                <ul className="text-muted-foreground space-y-0.5 text-xs">
                  {plan.samples.map((sample) => (
                    <li key={sample.sample_id}>
                      시료 <span className="font-mono">{sample.sample_name}</span>
                      {sample.lot_no && ` (로트 ${sample.lot_no})`} —{' '}
                      {sample.whole
                        ? '시료째 옮깁니다'
                        : `시편 ${sample.specimens}개만 — 같은 로트로 시료를 새로 만들어 붙입니다`}
                    </li>
                  ))}
                </ul>
              )}

              {plan.records.length > 0 && (
                <div className="rounded-md border px-3 py-2 text-xs">
                  <p className="font-medium">이 시험을 쓴 기록 {plan.records.length}개</p>
                  <p className="text-muted-foreground mt-0.5">
                    원 재료에 그때 계산한 기록으로 남습니다. 옮긴 뒤에 다시 묶으면 새 두께에서
                    계산됩니다.
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {plan.records.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
              )}

              {plan.blocked.length > 0 && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
                  <p className="font-medium">못 옮기는 것 {plan.blocked.length}개</p>
                  <ul className="mt-1 space-y-0.5">
                    {plan.blocked.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
              )}

              {plan.cards.length > 0 && (
                <div className="space-y-2">
                  <p className="font-medium">이 시험으로 만든 카드 {plan.cards.length}장</p>
                  <p className="text-muted-foreground text-xs">
                    옮기는 것은 막지 않습니다. 카드마다 <b>코멘트가 붙고</b>, 필요하면 정리(사용
                    중지)합니다 — 정리한 카드는 나중에 초안으로 되살릴 수 있습니다.
                  </p>
                  {plan.cards.map((card) => {
                    const action = actions[card.id] ?? 'note'
                    return (
                      <div
                        key={card.id}
                        className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="font-medium">{card.label}</span>{' '}
                          <Badge variant={card.status === 'published' ? 'default' : 'outline'}>
                            {STATUS_LABEL[card.status] ?? card.status}
                          </Badge>
                          <span className="text-muted-foreground ml-1 text-xs">
                            근거 시험 {card.test_runs}건이 옮겨집니다
                          </span>
                        </span>
                        <div
                          role="radiogroup"
                          aria-label={`${card.label} 처리`}
                          className="flex gap-1"
                        >
                          <Button
                            type="button"
                            size="sm"
                            variant={action === 'note' ? 'secondary' : 'ghost'}
                            role="radio"
                            aria-checked={action === 'note'}
                            onClick={() => setActions((now) => ({ ...now, [card.id]: 'note' }))}
                          >
                            코멘트만
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant={action === 'deprecate' ? 'secondary' : 'ghost'}
                            role="radio"
                            aria-checked={action === 'deprecate'}
                            disabled={!card.can_deprecate}
                            title={card.reason ?? '카드를 사용 중지하고 코멘트도 남깁니다'}
                            onClick={() =>
                              setActions((now) => ({ ...now, [card.id]: 'deprecate' }))
                            }
                          >
                            정리(사용 중지)
                          </Button>
                        </div>
                        {!card.can_deprecate && card.reason && (
                          <p className="text-muted-foreground w-full text-xs">{card.reason}</p>
                        )}
                      </div>
                    )
                  })}
                  <div className="space-y-1">
                    <Label htmlFor="relocate-comment" className="text-xs">
                      카드에 남길 말(선택)
                    </Label>
                    <Textarea
                      id="relocate-comment"
                      rows={2}
                      value={comment}
                      onChange={(event) => setComment(event.target.value)}
                      placeholder="예: 두께 오기 — 실측 1.2 mm"
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={!plan || plan.specimens === 0 || busy || planning}
          >
            {busy ? '옮기는 중…' : plan ? `시편 ${plan.specimens}개 옮기기` : '옮기기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
