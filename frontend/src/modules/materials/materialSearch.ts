/**
 * 재료 목록의 **상세 조건** — 이름 말고 다른 것으로 찾는다(2026-09-29).
 *
 * 찾기 상자의 자리표시가 「이름 · 별칭 · Grade 로 찾기」 였고, 실제로 그것밖에 못 찾았다
 * (지적: 이름·별칭·Grade 말고도 다른 조건으로). 사람이 재료를 떠올리는 말은 이름보다
 * 「범퍼에 쓰는」 「포스코에서 온」 「1.2 mm 안팎」 「인장을 잰」 「카드가 있는」 인 때가 많다.
 *
 * 폼 상태(문자열)와 서버 질의(숫자·단위)를 가르는 일을 여기서 한다 — 화면은 흉내 낼 것이
 * 많아 무겁고, 「무엇이 실리나」 는 여기서 잠근다.
 */

import { LENGTH_UNIT } from '@/modules/materials/api'
import type { MaterialQuery } from '@/modules/materials/api'

/** 폼 상태 — 칸마다 친 그대로. 빈 칸은 조건이 아니다. */
export interface MaterialDetail {
  use: string
  maker: string
  lot: string
  thicknessMin: string
  thicknessMax: string
  testType: string
  card: string
  registeredFrom: string
  registeredTo: string
}

export const EMPTY_DETAIL: MaterialDetail = {
  use: '',
  maker: '',
  lot: '',
  thicknessMin: '',
  thicknessMax: '',
  testType: '',
  card: '',
  registeredFrom: '',
  registeredTo: '',
}

/** 물성 카드 조건 — 서버의 `card` 값과 그 말. */
export const CARD_CHOICES = [
  { value: 'published', label: '확정 카드 있음' },
  { value: 'any', label: '카드 있음(초안 포함)' },
  { value: 'none', label: '카드 없음' },
] as const

function number(text: string): number | undefined {
  if (text.trim() === '') return undefined
  const value = Number(text)
  return Number.isFinite(value) ? value : undefined
}

/**
 * 폼 → 서버 질의. **빈 칸은 보내지 않는다** — `use=` 를 보내면 서버가 빈 조건으로 한 번 더
 * 훑는다.
 *
 * 두께는 **화면 단위(mm)로 보내고 단위를 함께 적는다.** 단위 없이 1.2 를 보내면 서버는 SI 로
 * 읽어 1.2 m 가 된다 — 두께 칸이 같은 자리에서 걸렸다(2026-09-24).
 */
export function detailQuery(detail: MaterialDetail): Partial<MaterialQuery> {
  const low = number(detail.thicknessMin)
  const high = number(detail.thicknessMax)
  const made: Partial<MaterialQuery> = {
    use: detail.use.trim() || undefined,
    maker: detail.maker.trim() || undefined,
    lot: detail.lot.trim() || undefined,
    thickness_min: low,
    thickness_max: high,
    thickness_unit: low !== undefined || high !== undefined ? LENGTH_UNIT : undefined,
    test_type: detail.testType || undefined,
    card: detail.card || undefined,
    registered_from: detail.registeredFrom || undefined,
    registered_to: detail.registeredTo || undefined,
  }
  return Object.fromEntries(
    Object.entries(made).filter(([, value]) => value !== undefined)
  ) as Partial<MaterialQuery>
}

/** 걸린 조건 수 — 「상세 조건 · 3」. 두께 범위는 끝이 둘이어도 조건 하나다. */
export function detailCount(detail: MaterialDetail): number {
  const query = detailQuery(detail)
  const keys = Object.keys(query).filter(
    (key) => key !== 'thickness_unit' && key !== 'thickness_max' && key !== 'registered_to'
  )
  let count = keys.length
  // 끝 하나만 적었어도 조건이다 — 위에서 뺀 짝을 되살린다.
  if (query.thickness_max !== undefined && query.thickness_min === undefined) count += 1
  if (query.registered_to !== undefined && query.registered_from === undefined) count += 1
  return count
}

export function sameDetail(left: MaterialDetail, right: MaterialDetail): boolean {
  return (Object.keys(EMPTY_DETAIL) as (keyof MaterialDetail)[]).every(
    (key) => left[key] === right[key]
  )
}
