/**
 * 같은 재료를 두 번 등록한 것을 **하나로 합치는 창**(2026-11-17, VOC 59 · ADR 0092).
 *
 * 시료 이동은 시료만 옮겨, 재료에 직접 붙은 것(선언 물성 · 밀도 · 카드 · 묶음 기록 …)이 빈 재료와 함께
 * 휴지통으로 갔다. 여기서는 받을 재료를 고르면 서버가 무엇이 어디로 가는지 세어 보인다 — 받는 재료가
 * 비어 있는 칸만 채우고, **값이 다르면 받는 재료의 값을 둔다**(두 값을 함께 보인다). 이 재료는
 * 휴지통으로 간다(되살릴 수 있다). 막히는 까닭이 하나라도 있으면 합치지 않는다.
 */

import { useEffect, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { Material, MaterialMergePlan, MaterialMergeResult } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
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
import { Textarea } from '@/shared/components/ui/textarea'

/** 옮기는 것 — 0 인 줄은 보이지 않는다. */
function moving(plan: MaterialMergePlan): string[] {
  const rows: [number, string][] = [
    [plan.samples, `시료 ${plan.samples}개(시편 ${plan.specimens}개 · 시험 ${plan.test_runs}건)`],
    [plan.cards, `카드 ${plan.cards}장`],
    [plan.groups, `묶음 기록 ${plan.groups}개`],
    [plan.ensembles, `저장한 대표 곡선 ${plan.ensembles}개`],
    [plan.parameter_sets, `계수 묶음 ${plan.parameter_sets}벌`],
    [plan.catalog_link ? 1 : 0, '문헌 연결'],
    [plan.workbench_items, `워크벤치에 담긴 줄 ${plan.workbench_items}개`],
    [plan.bom_aliases, `BOM 이름 매칭 ${plan.bom_aliases}개`],
    [plan.parts, `적용 부품 ${plan.parts}줄(복사)`],
  ]
  return rows.filter(([count]) => count > 0).map(([, text]) => text)
}

export function MaterialMergeDialog({
  open,
  materialId,
  materialName,
  onClose,
  onDone,
}: {
  open: boolean
  materialId: string
  materialName: string
  onClose: () => void
  onDone: (result: MaterialMergeResult) => void
}) {
  const [target, setTarget] = useState<Material | null>(null)
  const [plan, setPlan] = useState<MaterialMergePlan | null>(null)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 열 때마다 새로 — 지난번에 고른 재료가 남으면 다른 재료에 그대로 걸린다.
  useEffect(() => {
    if (!open) return
    setTarget(null)
    setPlan(null)
    setComment('')
    setError(null)
  }, [open])

  // **고르면 서버에 묻는다** — 무엇이 막히고 어느 값이 다른지는 서버가 안다.
  useEffect(() => {
    if (!open || !target) return
    let cancelled = false
    setPlan(null)
    setError(null)
    materialsApi
      .mergePlan(materialId, target.id)
      .then((found) => {
        if (!cancelled) setPlan(found)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught : new Error('계획을 받지 못했습니다.'))
      })
    return () => {
      cancelled = true
    }
  }, [open, target, materialId])

  async function submit() {
    if (!plan || !target) return
    setBusy(true)
    setError(null)
    try {
      const done = await materialsApi.merge(materialId, target.id, comment.trim() || null)
      onDone(done)
      onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('합치지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const blocked = plan?.blocked ?? []
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>다른 재료와 합치기</DialogTitle>
          <DialogDescription>
            <b>{materialName}</b> 의 시료 · 카드 · 기록을 고른 재료로 옮기고 이 재료는 휴지통으로
            보냅니다(되살리기 가능). 분류(Family · Category · Grade)가 같은 재료만 고를 수 있고,
            두 재료의 값이 다르면 <b>받는 재료의 값</b>을 둡니다.
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
            <div className="space-y-3" aria-label="합치기 계획">
              <p className="font-mono text-xs">
                {plan.source_name} → <b>{plan.target_name}</b>
              </p>
              <Section title="옮기는 것" lines={moving(plan)} empty="옮길 것이 없습니다" />
              <Section title="받는 재료에 없어 가져오는 값" lines={plan.taken} />
              <Section
                title="값이 달라 받는 재료의 것을 두는 칸"
                lines={plan.kept}
                tone="amber"
                note="받는 재료를 고쳐야 하면 합친 뒤 그 재료에서 고치세요."
              />
              <Section title="옛 재료에 남는 것" lines={plan.left} />
              {blocked.length > 0 && (
                <Section title="합칠 수 없는 까닭" lines={blocked} tone="amber" />
              )}
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">
                  코멘트(카드 · 변경 이력에 함께 남음)
                </span>
                <Textarea
                  aria-label="합치기 코멘트"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="예: 같은 재료를 두 번 등록함 — DP 590 을 DP590 으로"
                  rows={2}
                />
              </label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button onClick={() => void submit()} disabled={!plan || blocked.length > 0 || busy}>
            {busy ? '합치는 중…' : '합치기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Section({
  title,
  lines,
  empty,
  tone,
  note,
}: {
  title: string
  lines: string[]
  empty?: string
  tone?: 'amber'
  note?: string
}) {
  if (lines.length === 0 && !empty) return null
  return (
    <section
      aria-label={title}
      className={
        tone === 'amber'
          ? 'rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2'
          : 'rounded-md border px-3 py-2'
      }
    >
      <p className="font-medium">{title}</p>
      {lines.length === 0 ? (
        <p className="text-muted-foreground mt-1">{empty}</p>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {note && lines.length > 0 && <p className="text-muted-foreground mt-1 text-xs">{note}</p>}
    </section>
  )
}
