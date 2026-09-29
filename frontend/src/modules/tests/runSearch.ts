/**
 * 시험 목록의 **상세 조건** — 이름 말고 다른 것으로 찾는다(2026-09-29).
 *
 * 시험일 기간 · 장비 · **시험 조건의 범위**(「80~100 °C 에서 잰 것」). 조건은 부서마다 칸
 * 이름이 달라(`temp`·`temperature`) 표준 조건 키로 묻는다 — 서버가 그 키에 이어진 칸을 찾는다.
 *
 * ## 조건 값은 화면 단위로 보내고 단위를 함께 적는다
 *
 * 온도는 °C 로 친다. 단위 없이 80 을 보내면 서버는 모른다고 거절한다 — 짐작하면 80 K 가 되어
 * 조용히 틀린다. 단위는 **표(`shared/units`)에서 읽는다** — 라벨과 보내는 단위가 한 곳에서 온다.
 */

import type { StandardCondition } from '@/modules/tests/api'
import { display } from '@/shared/units'

export interface RunDetail {
  testedFrom: string
  testedTo: string
  instrument: string
  condition: string
  conditionMin: string
  conditionMax: string
}

export const EMPTY_RUN_DETAIL: RunDetail = {
  testedFrom: '',
  testedTo: '',
  instrument: '',
  condition: '',
  conditionMin: '',
  conditionMax: '',
}

/** 상세 조건이 쓰는 질의 키 — 다시 걸 때 옛 값을 먼저 걷어 낸다. */
export const RUN_DETAIL_KEYS = [
  'tested_from',
  'tested_to',
  'instrument',
  'condition',
  'condition_unit',
  'condition_min',
  'condition_max',
] as const

/** 이 조건을 화면에서 받는 단위. 표에 없으면 SI 그대로(무차원은 `1`). */
export function conditionUnit(standard: Pick<StandardCondition, 'si_unit'>): string {
  return display(standard.si_unit).unit || standard.si_unit
}

function number(text: string): string | undefined {
  if (text.trim() === '') return undefined
  return Number.isFinite(Number(text)) ? String(Number(text)) : undefined
}

/**
 * 폼 → 서버 질의. **빈 칸은 보내지 않는다.**
 *
 * 조건은 **끝이 하나라도 있어야** 싣는다 — 조건만 고르고 범위를 안 적으면 서버가 거절하고,
 * 사람에게는 「고르기만 했는데 오류」 로 보인다. 모르는 조건 키도 싣지 않는다.
 */
export function runDetailQuery(
  detail: RunDetail,
  standards: Pick<StandardCondition, 'key' | 'si_unit'>[]
): Record<string, string> {
  const made: Record<string, string | undefined> = {
    tested_from: detail.testedFrom || undefined,
    tested_to: detail.testedTo || undefined,
    instrument: detail.instrument || undefined,
  }
  const standard = standards.find((one) => one.key === detail.condition)
  const low = number(detail.conditionMin)
  const high = number(detail.conditionMax)
  if (standard && (low !== undefined || high !== undefined)) {
    made.condition = standard.key
    made.condition_unit = conditionUnit(standard)
    made.condition_min = low
    made.condition_max = high
  }
  return Object.fromEntries(
    Object.entries(made).filter((entry): entry is [string, string] => entry[1] !== undefined)
  )
}

/**
 * 걸린 조건 수 — 「상세 조건 · 2」. **실제로 걸린 질의에서 센다** — 폼에서 세면 적고 안 건
 * 것까지 센다. 기간·범위는 끝이 둘이어도 하나로 센다.
 */
export function runDetailCount(query: Record<string, unknown>): number {
  const on = (key: string) => query[key] !== undefined && query[key] !== ''
  return (
    (on('tested_from') || on('tested_to') ? 1 : 0) +
    (on('instrument') ? 1 : 0) +
    (on('condition') ? 1 : 0)
  )
}

export function sameRunDetail(left: RunDetail, right: RunDetail): boolean {
  return (Object.keys(EMPTY_RUN_DETAIL) as (keyof RunDetail)[]).every(
    (key) => left[key] === right[key]
  )
}
