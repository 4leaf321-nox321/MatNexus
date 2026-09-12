/**
 * 카드의 종류 — **목록을 가르는 열쇠.**
 *
 * 한 재료에 경화식·선형탄성구간·점탄성·재료 기본 정보 카드가 섞여 쌓이면 이름만으로는
 * 무엇이 무엇인지 안 보인다(2026-09-05). 카드가 든 블록 가운데 **가장 특징적인 것**이
 * 종류다 — 탄성 블록은 거의 모든 카드에 들어 있어 종류가 못 된다.
 *
 * 이름도 순서도 블록 선언(`fittingApi.blocks`)에서 읽는다 — `kind_priority` 가 작을수록
 * 먼저, `null` 은 종류가 아니다. 여기 블록 이름을 적어 두면 확장이 블록을 더해도 종류가
 * 안 생기고(2026-09-12), 선언이 바뀌었을 때 칩만 옛 이름을 든다.
 */

import type { BlockSpec, PropertyCard } from '@/modules/fitting/api'

/** 종류가 되는 블록, 우선순위 차례. 선언이 아직 안 왔으면 빈 목록이다. */
function defining(specs: BlockSpec[]): BlockSpec[] {
  return specs
    .filter((spec) => spec.kind_priority !== null && spec.kind_priority !== undefined)
    .sort((a, b) => (a.kind_priority ?? 0) - (b.kind_priority ?? 0))
}

/**
 * 블록 이름과 카드 종류 이름이 다른 것. 경화식 블록이 든 카드는 탄성계수 + 소성 표까지
 * 들어 덱에서 *ELASTIC + *PLASTIC 으로 나간다 — 카드로서는 「탄소성」 이다(2026-09-05,
 * 「경화식 카드」 가 무슨 카드인지 안 읽혔다). 블록 자체의 이름(경화식)은 그대로다.
 */
const KIND_LABELS: Record<string, string> = { hardening: '탄소성' }

export const DECLARED_KIND = '재료 기본 정보'

export function cardKind(card: PropertyCard, specs: BlockSpec[]): string {
  const blocks = Object.keys(card.blocks ?? {})
  const found = defining(specs).find((spec) => blocks.includes(spec.key))
  if (found) return KIND_LABELS[found.key] ?? found.label
  // 시험 없이 적어 둔 값만으로 만든 카드 — 블록은 탄성뿐이다.
  if (card.test_type_key === null) return DECLARED_KIND
  return specs.find((spec) => spec.key === 'elastic')?.label ?? '탄성'
}
