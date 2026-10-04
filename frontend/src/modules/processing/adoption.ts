/**
 * 채택 검토대의 셈 — **무엇을 기본으로 고르나, 어느 것이 튀나**(ADR 0058).
 *
 * 화면과 떼어 둔 이유: 여기가 틀리면 사람은 튀는 시험을 못 보고 채택한다. 그 판단은 그림이
 * 아니라 숫자라서 시험이 숫자로 묶을 수 있어야 한다(`adoption.test.ts`).
 */

import type { ProcessingScalar, ResultBrief, RunOverview } from '@/modules/processing/api'
import { HEADLINE } from '@/modules/processing/batchRun'

/** 중앙값에서 이만큼 멀면 칠한다. 사람이 바꾼다 — 재료마다 흩어짐이 다르다. */
export const DEFAULT_THRESHOLD = 0.1

/**
 * 처음에 고를 결과. **지금 채택이 있으면 그것** — 안 바꾸는 것이 기본이어야 「한 번에 채택」
 * 이 이미 정한 것을 말없이 옮기지 않는다. 없으면 **원본이 바뀌기 전의 것이 아닌 가장 최근**,
 * 그것도 없으면 가장 최근.
 */
export function defaultChoice(run: RunOverview): string | null {
  if (run.adopted_result_id && run.results.some((one) => one.id === run.adopted_result_id)) {
    return run.adopted_result_id
  }
  return (run.results.find((one) => !one.stale) ?? run.results[0])?.id ?? null
}

/** 고른 결과. 고른 것이 목록에 없으면(지워졌다) 기본으로 돌아간다. */
export function chosenOf(
  run: RunOverview,
  picked: Record<string, string> | undefined
): ResultBrief | null {
  const wanted = picked?.[run.test_run_id] ?? defaultChoice(run)
  return (
    run.results.find((one) => one.id === wanted) ??
    run.results.find((one) => one.id === defaultChoice(run)) ??
    null
  )
}

/** 중앙값과의 차이 하나 — 가장 먼 값으로 그 시험을 말한다. */
export interface Spread {
  key: string
  label: string
  /** (값 − 중앙값) / |중앙값|. 부호를 지킨다 — 높게 튄 것과 낮게 튄 것은 다른 이야기다. */
  ratio: number
}

/**
 * 견줄 값들 — **같은 시험 종류끼리만.** 인장과 DMA 의 값은 견줄 것이 없다.
 *
 * 인장이면 탄성계수 · 항복강도 · 인장강도(배치 화면과 같은 차례). 그 셋이 없는 종류면 결과의
 * 절반 이상이 가진 값 중 흔한 것 셋 — 종류마다 이름을 여기 적어 두면 새 계산이 생길 때
 * 이 화면만 옛 목록을 든다.
 */
export function keysToCompare(results: ResultBrief[]): string[] {
  const counts = new Map<string, number>()
  for (const one of results) {
    for (const scalar of one.scalars) counts.set(scalar.key, (counts.get(scalar.key) ?? 0) + 1)
  }
  const headline = HEADLINE.filter((key) => counts.has(key))
  if (headline.length > 0) return headline
  return [...counts.entries()]
    .filter(([, count]) => count * 2 >= results.length)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([key]) => key)
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

/**
 * 견주는 묶음 — **같은 재료 · 같은 시험 종류 · 같은 방향.** 반복 시편끼리만 견준다.
 *
 * 처음에는 시험 종류로만 묶었다. 개발 DB 에서 채택 전 47건을 열어 보니 재료가 여섯 가지
 * 섞여 있었고, 206 GPa 강판이 수지 시험들의 중앙값(3.7 GPa)에 대어 「+5405%」 로 섰다 —
 * 47건 중 41건이 「먼 것」 이라 칠한 것이 아무것도 가리키지 않았다(2026-10-04). 방향도
 * 가른다 — 이방성 재료의 MD 와 TD 는 다른 것이 정상이다.
 */
export function groupOf(run: RunOverview): string {
  return [run.test_type_key ?? '?', run.material_id ?? '?', run.orientation ?? ''].join('|')
}

/**
 * 시험마다 중앙값에서 가장 먼 값. **같은 묶음 안에서만**(`groupOf`) 센다.
 *
 * 견줄 것이 둘 미만이면 `null` 이다 — 하나뿐인 값은 자기 자신이 중앙값이라 늘 0 이고, 0 을
 * 보이면 「튀지 않는다」 로 읽힌다(모르는 것을 괜찮다고 말하게 된다).
 */
export function spreadsOf(
  runs: RunOverview[],
  choose: (run: RunOverview) => ResultBrief | null
): Map<string, Spread | null> {
  const out = new Map<string, Spread | null>()
  const groups = new Map<string, { run: RunOverview; result: ResultBrief }[]>()
  for (const run of runs) {
    const result = run.found ? choose(run) : null
    if (!result) {
      out.set(run.test_run_id, null)
      continue
    }
    const key = groupOf(run)
    groups.set(key, [...(groups.get(key) ?? []), { run, result }])
  }

  for (const members of groups.values()) {
    const keys = keysToCompare(members.map((one) => one.result))
    const medians = new Map<string, number>()
    for (const key of keys) {
      const values = members
        .map((one) => one.result.scalars.find((scalar) => scalar.key === key)?.value)
        .filter((value): value is number => value !== undefined && Number.isFinite(value))
      if (values.length >= 2) medians.set(key, median(values))
    }
    for (const { run, result } of members) {
      let far: Spread | null = null
      for (const [key, middle] of medians) {
        const scalar = result.scalars.find((one) => one.key === key)
        if (!scalar || middle === 0) continue
        const ratio = (scalar.value - middle) / Math.abs(middle)
        if (far === null || Math.abs(ratio) > Math.abs(far.ratio)) {
          far = { key, label: scalar.label, ratio }
        }
      }
      out.set(run.test_run_id, far)
    }
  }
  return out
}

/** 줄에 보일 핵심 값 — 견주는 값과 같은 것, 같은 차례. */
export function headlineOf(result: ResultBrief, keys: string[]): ProcessingScalar[] {
  return keys
    .map((key) => result.scalars.find((one) => one.key === key))
    .filter((one): one is ProcessingScalar => one !== undefined)
}
