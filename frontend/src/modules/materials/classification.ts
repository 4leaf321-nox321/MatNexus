/**
 * 분류를 세는 규칙 — **목록 화면과 옆패널이 같은 것을 쓴다.**
 *
 * 두 벌로 두면 한쪽에만 규칙이 늘거나 갈린다. 실제로 시료 폼에서 겪은 일이고
 * (`OptionPicker` 의 주석), `NewSampleDialog`·`SpecimenPicker` 가 같은 이유로
 * 폼을 공유한다.
 */

import type { Classification } from '@/modules/materials/api'
import type { Option } from '@/shared/components/OptionPicker'

/**
 * 같은 이름끼리 개수를 합친다.
 *
 * 서버는 (Family, Category) 쌍으로 세어 주므로 Family 하나가 여러 줄에 걸쳐
 * 있다 — Metal/Steel 58, Metal/Aluminum 3. Family 목록에는 61 로 합쳐 보여야
 * "Metal 을 고르면 몇 건인가" 가 맞는다.
 */
export function tally(pairs: [string, number][]): Option[] {
  const sums = new Map<string, number>()
  for (const [name, count] of pairs) sums.set(name, (sums.get(name) ?? 0) + count)
  return [...sums].map(([value, count]) => ({ value, count }))
}

/** 쓰이고 있는 Family 들. */
export function familiesOf(rows: Classification[]): Option[] {
  return tally(rows.map((item) => [item.family, item.count]))
}

/**
 * 그 Family 안의 Category 들. **Family 를 고르면 그 안만 남긴다.**
 *
 * 안 그러면 `Metal + PP` 처럼 **결과가 늘 0건인 조합**을 고를 수 있고, 사람은
 * 재료가 없는 줄 안다.
 */
export function categoriesOf(rows: Classification[], family: string): Option[] {
  return tally(
    rows.filter((item) => !family || item.family === family).map((item) => [item.category, item.count])
  )
}
