/**
 * 규격이 정한 **공칭 치수**를 화면 단위로 바꾼다.
 *
 * ## 왜 따로 두는가
 *
 * 단위 환산이다. 조용히 틀리는 자리라 화면에서 떼어 놓고 시험을 건다 —
 * `0.05 m` 를 `0.05` 로 보여 주면 사람은 게이지가 0.05 mm 인 줄 알고, 그
 * 숫자를 믿고 두께를 그에 맞춰 적는다. 틀린 것이 화면에만 있으면 아무도 못
 * 본다.
 *
 * ## 값을 칸에 베끼지 않는다
 *
 * 여기서 나온 것은 **흐린 글씨(placeholder)로만** 쓴다. 치수는
 * `run → measured → nominal` 순으로 풀리는데(`specimen_size.sizes_of`),
 * 공칭을 실측 칸에 적으면 그 구분이 사라진다. 나중에 그 시편을 실제로 쟀을
 * 때 어느 것이 잰 값이었는지 알 수 없다.
 */

import { toDisplay } from '@/shared/units'
import type { SpecimenField } from '@/modules/vocabulary/api'

/** 일괄 등록 줄의 치수 칸. */
export type SizeKey = 'thickness' | 'width' | 'gauge'

/**
 * 줄의 칸 이름 ↔ 규격이 들고 있는 이름. **게이지만 이름이 다르다** —
 * 규격 쪽은 `gauge_length` 다.
 */
export const SIZE_FIELDS: readonly (readonly [SizeKey, string, string])[] = [
  ['thickness', 'thickness', '두께'],
  ['width', 'width', '폭'],
  ['gauge', 'gauge_length', '게이지'],
]

/** 규격이 준 공칭 — 화면 단위의 문자열. 규격에 없는 칸은 빠진다. */
export type Nominal = Partial<Record<SizeKey, string>>

/**
 * 규격 값의 `attributes` 에서 치수를 골라 화면 단위로 바꾼다.
 *
 * **저장 단위는 칸이 말한다.** 길이라고 `'m'` 을 박아 두면 규격이 각도나
 * 넓이를 갖게 되는 날 조용히 틀린다. 칸을 못 찾으면 그 값은 버린다 —
 * 단위를 모르는 숫자를 보여 주는 것이 안 보여 주는 것보다 나쁘다.
 */
export function nominalSizes(
  attributes: Record<string, number | string> | undefined,
  fields: readonly SpecimenField[]
): Nominal {
  const shown: Nominal = {}
  for (const [slot, key] of SIZE_FIELDS) {
    const raw = attributes?.[key]
    if (typeof raw !== 'number' || !Number.isFinite(raw)) continue
    const field = fields.find((one) => one.key === key)
    if (!field) continue
    // 0.0125 m → 12.5 mm. `toPrecision` 은 2.5000000000000004 를 막는다.
    shown[slot] = String(Number(toDisplay(raw, field.si_unit, field.dimension).toPrecision(6)))
  }
  return shown
}
