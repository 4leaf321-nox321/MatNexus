/**
 * 요약값을 **장비 / 우리** 로 짝지어 나란히 놓는다.
 *
 * `TestSummary` 는 `(시험, key, source)` 로 유일하다 — 같은 항목에 장비 값과 우리
 * 값이 나란히 서게 설계돼 있었다. 그런데 화면이 그것을 **한 줄씩 평평하게** 그려
 * 서, 같은 항복강도가 표의 다른 자리에 떨어져 있었다. 나란히 두려고 source 를
 * 나눈 것인데 정작 비교가 안 됐다.
 *
 * 실측: 같은 시험에서 장비 160.0 MPa, 우리 249.5 MPa — **56% 차이**다. 표를 눈으로
 * 훑어 짝을 찾아야 알 수 있었다.
 *
 * ## 차이를 계산하되 판정하지 않는다
 *
 * 몇 % 다른지는 계산해서 보여 준다. 그러나 **어느 쪽이 맞는지는 말하지 않는다** —
 * 우리 레시피가 틀렸을 수도 있고(탄성 구간을 잘못 잡으면 항복강도가 크게 어긋난다),
 * 장비 설정이 다를 수도 있다. 그 판단은 곡선을 본 사람이 한다. 처리 단계에서
 * 네킹을 후보로만 제시하는 것과 같은 태도다.
 */

export interface SummaryRow {
  key: string
  label: string | null
  source: string
  value: number | null
  text: string | null
  si_unit: string | null
  dimension?: string | null
}

export interface SummaryPair {
  key: string
  label: string
  si_unit: string | null
  dimension: string | null
  instrument: SummaryRow | null
  ours: SummaryRow | null
  /**
   * 우리 값이 장비 값보다 몇 % 큰가. 둘 다 숫자일 때만 있다.
   *
   * 기준을 장비로 잡는 이유: 장비 값이 **먼저 있던 값**이다. 우리 계산을 붙이는
   * 쪽이 나중이므로 "얼마나 벌어졌나" 를 그 기준에서 읽는 것이 자연스럽다.
   */
  differencePercent: number | null
}

/** 이 이상 벌어지면 화면이 눈에 띄게 표시한다. **버리거나 고치지는 않는다.** */
export const NOTABLE_DIFFERENCE = 5

export function pairSummaries(rows: SummaryRow[]): SummaryPair[] {
  const byKey = new Map<string, SummaryPair>()

  for (const row of rows) {
    let pair = byKey.get(row.key)
    if (!pair) {
      pair = {
        key: row.key,
        label: row.label ?? row.key,
        si_unit: row.si_unit,
        dimension: row.dimension ?? null,
        instrument: null,
        ours: null,
        differencePercent: null,
      }
      byKey.set(row.key, pair)
    }
    if (row.source === 'matnexus') pair.ours = row
    else pair.instrument = row

    // **라벨은 우리 것을 먼저 쓴다.** 장비 라벨은 원문 그대로라 영어이고
    // `k{lo 10 - 15}` 같은 장비 표기가 붙는다. 우리 것이 없을 때만 쓴다.
    if (row.source === 'matnexus' && row.label) pair.label = row.label
    else if (!pair.ours && row.label) pair.label = row.label

    // 차원도 우리 것이 우선이다 — 장비 값에는 대개 비어 있다.
    if (row.dimension) pair.dimension = row.dimension
    if (row.si_unit) pair.si_unit = row.si_unit
  }

  for (const pair of byKey.values()) {
    const a = pair.instrument?.value
    const b = pair.ours?.value
    // 0 으로 나누지 않는다. 기준이 0 이면 '몇 %' 라는 질문 자체가 성립하지 않는다.
    if (a != null && b != null && a !== 0) {
      pair.differencePercent = ((b - a) / Math.abs(a)) * 100
    }
  }

  // **짝이 있는 것을 위로.** 비교가 이 표의 목적이고, 한쪽만 있는 값은 참고다.
  return [...byKey.values()].sort((left, right) => {
    const paired = Number(Boolean(right.instrument && right.ours)) -
      Number(Boolean(left.instrument && left.ours))
    return paired !== 0 ? paired : left.key.localeCompare(right.key)
  })
}
