/**
 * 통계 묶음의 **시험 온도** — 묶음 열쇠는 시험 종류 · 방향 · 온도다(2026-11-15).
 *
 * 전에는 (종류, 방향)뿐이라 23 °C 5건과 80 °C 3건이 한 평균 · 대표 곡선 · 카드가 됐다. 서버가
 * 온도로 가르고(첫 값과 2 K 이내면 한 묶음), 묶음마다 `temperature_k`(K, `null` 은 미기재)를
 * 준다. 카드 · 맞춰 보기 · 분포 요청은 그 값을 그대로 돌려보낸다 — 그 방향에 묶음이 둘 이상인데
 * 안 보내면 서버가 422 로 「온도를 고르세요」.
 *
 * 표시는 단위 표(`shared/units`)를 거친다 — `- 273.15` 를 여기 적지 않는다.
 */

import { formatCondition } from '@/shared/units'

export interface TemperatureGroup {
  test_type_key: string
  orientation: string
  temperature_k?: number | null
}

/** 사람이 읽는 시험 온도 — `80 °C`, 미기재면 「온도 미기재」. */
export function temperatureText(kelvin: number | null | undefined): string {
  if (kelvin == null) return '온도 미기재'
  return formatCondition({ temperature_k: kelvin }) ?? '온도 미기재'
}

/** 묶음 하나를 가리키는 열쇠 — React `key` · 펼침 상태에 쓴다. 온도까지 넣어야 겹치지 않는다. */
export function groupKey(one: TemperatureGroup): string {
  return `${one.test_type_key}-${one.orientation}-${one.temperature_k ?? 'none'}`
}

/** 같은 묶음인가 — 종류 · 방향 · 온도(서버가 준 대표 온도라 그대로 견준다). */
export function sameGroup(
  a: TemperatureGroup | null | undefined,
  b: TemperatureGroup | null | undefined
): boolean {
  if (!a || !b) return false
  return (
    a.test_type_key === b.test_type_key &&
    a.orientation === b.orientation &&
    (a.temperature_k ?? null) === (b.temperature_k ?? null)
  )
}

/**
 * 같은 종류 · 방향에 **다른 온도의 묶음이 있나** — 있으면 단추 · 이름에 온도를 붙인다. 온도가
 * 하나뿐이거나 전부 미기재인 재료는 전과 똑같이 보인다.
 */
export function hasTemperatureSiblings(
  one: TemperatureGroup,
  all: readonly TemperatureGroup[]
): boolean {
  return all.some(
    (other) =>
      other.test_type_key === one.test_type_key &&
      other.orientation === one.orientation &&
      (other.temperature_k ?? null) !== (one.temperature_k ?? null)
  )
}

/** 이름 뒤에 붙일 온도 — 「 · 80 °C」. 미기재면 붙이지 않는다(상온이라고 단정하지 않는다). */
export function temperatureSuffix(kelvin: number | null | undefined): string {
  return kelvin == null ? '' : ` · ${temperatureText(kelvin)}`
}
