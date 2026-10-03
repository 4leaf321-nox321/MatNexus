/**
 * 의뢰 항목의 **방향 · 수량대로 시편을 한꺼번에** 만든다(2026-10-03, [계획] 측정 의뢰 2단계).
 *
 * 전에는 「시험 등록」 창의 「새 시편」 으로 한 개씩 만들었다 — MD 3 · TD 3 이면 여섯 번을 눌렀다.
 * 수량은 항목의 **합계**라 방향에 고르게 나눈 안을 먼저 보이고, 방향마다 고칠 수 있게 한다.
 * 이 시료에 이미 있는 시편 수를 함께 보인다 — 모르고 누르면 같은 시편이 두 벌 생긴다.
 *
 * 하나씩 차례로 만든다(같은 시료의 채번이 엉키지 않게). 중간에 막히면 거기서 멈추고 몇 개를
 * 만들었는지 말한다.
 */

import { useEffect, useState } from 'react'

import { splitByOrientation } from '@/modules/commissions/itemConditions'
import type { CommissionItem } from '@/modules/commissions/api'
import { LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
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
import { useResource } from '@/shared/hooks/useResource'

export function SpecimensForItemDialog({
  open,
  sampleId,
  item,
  onClose,
  onMade,
}: {
  open: boolean
  sampleId: string
  item: Pick<CommissionItem, 'position' | 'orientations' | 'count'>
  onClose: () => void
  /** 만든 수 — 0 이 아닐 때만 부른다. */
  onMade: (count: number) => void
}) {
  const existing = useResource(
    () => (open ? materialsApi.specimens(sampleId) : Promise.resolve([])),
    [open, sampleId]
  )
  const [plan, setPlan] = useState(() => splitByOrientation(item))
  const [busy, setBusy] = useState(false)
  const [madeSoFar, setMadeSoFar] = useState(0)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (open) {
      setPlan(splitByOrientation(item))
      setMadeSoFar(0)
      setError(null)
    }
  }, [open, item])

  const total = plan.reduce((sum, one) => sum + one.count, 0)
  const have = (orientation: string) =>
    (existing.data ?? []).filter((one) => one.orientation === orientation).length

  async function make() {
    setBusy(true)
    setError(null)
    let made = 0
    try {
      for (const one of plan) {
        for (let at = 0; at < one.count; at += 1) {
          // 치수는 비운다 — 두께 · 폭은 시편 줄에서 나중에 적는다(시험 등록 창과 같다).
          await materialsApi.createSpecimen(sampleId, {
            orientation: one.orientation,
            length_unit: LENGTH_UNIT,
          })
          made += 1
          setMadeSoFar(made)
        }
      }
      onMade(made)
      onClose()
    } catch (caught) {
      setError(
        caught instanceof Error
          ? new Error(`${made}개를 만들고 멈췄습니다 — ${caught.message}`)
          : new Error(`${made}개를 만들고 멈췄습니다.`)
      )
      if (made > 0) onMade(made)
      void existing.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{item.position + 1}번 항목의 시편 만들기</DialogTitle>
          <DialogDescription>
            항목의 수량 {item.count}개를 방향에 나눴습니다. 방향마다 고칠 수 있습니다 — 이미 있는
            시편을 쓰려면 그만큼 줄이세요.
          </DialogDescription>
        </DialogHeader>
        <ErrorNotice error={error} />
        <ul className="space-y-2 text-sm">
          {plan.map((one, at) => (
            <li key={one.orientation} className="flex items-center gap-2">
              <span className="w-12 font-medium">{one.orientation}</span>
              <Input
                type="number"
                min={0}
                max={200}
                className="h-8 w-20"
                aria-label={`${one.orientation} 시편 수`}
                value={one.count}
                disabled={busy}
                onChange={(event) =>
                  setPlan((current) =>
                    current.map((row, index) =>
                      index === at
                        ? { ...row, count: Math.max(0, Math.min(200, Number(event.target.value) || 0)) }
                        : row
                    )
                  )
                }
              />
              <span className="text-muted-foreground">
                {existing.data ? `이 시료에 이미 ${have(one.orientation)}개` : ''}
              </span>
            </li>
          ))}
        </ul>
        {busy && (
          <p className="text-sm" role="status">
            {madeSoFar} / {total} 만드는 중…
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            닫기
          </Button>
          <Button disabled={busy || total === 0} onClick={() => void make()}>
            시편 {total}개 만들기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
