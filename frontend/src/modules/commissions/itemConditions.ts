/**
 * 의뢰 항목의 조건(SI) → 등록 창의 칸(표시 단위 글자).
 *
 * 의뢰 상세의 「시험 등록」 과 일괄 등록(`/tests/upload?commission=…&item=…`)이 **같은 변환을
 * 쓴다**(2026-10-03) — 둘이 따로 고치면 같은 항목이 두 등록 자리에서 다른 숫자로 채워진다.
 */

import type { CommissionItem } from '@/modules/commissions/api'
import type { TestType } from '@/modules/tests/api'
import { toDisplay } from '@/shared/units'

/** 항목의 조건(SI)을 등록 창의 칸(표시 단위 글자)으로. 단위 없는 칸은 그대로. */
export function presetConditions(
  item: Pick<CommissionItem, 'conditions'>,
  testType: TestType | undefined
): Record<string, string> {
  const out: Record<string, string> = {}
  for (const field of testType?.conditions ?? []) {
    const raw = item.conditions[field.key]
    if (raw === undefined || raw === null || raw === '') continue
    out[field.key] =
      typeof raw === 'number' && field.si_unit
        ? String(Number(toDisplay(raw, field.si_unit, field.dimension).toPrecision(6)))
        : String(raw)
  }
  return out
}

/**
 * 항목의 수량을 방향에 고르게 나눈다 — 수량은 **합계**다(진행률이 그 합으로 센다). 나머지는
 * 앞 방향부터 하나씩. 방향을 안 정했으면 `NA` 하나에 전부.
 */
export function splitByOrientation(
  item: Pick<CommissionItem, 'orientations' | 'count'>
): { orientation: string; count: number }[] {
  const orientations = item.orientations.length > 0 ? item.orientations : ['NA']
  const base = Math.floor(item.count / orientations.length)
  const extra = item.count % orientations.length
  return orientations.map((orientation, at) => ({
    orientation,
    count: base + (at < extra ? 1 : 0),
  }))
}
