/**
 * 이 단계 구성으로 **나중에 못 하게 되는 일**.
 *
 * 실측으로 드러난 함정: 공칭까지만 계산하는 레시피로 20건을 처리하고 채택까지
 * 마친 뒤, CAE 카드 탭에서 "strain_true_plastic·stress_true 열이 없습니다" 를
 * 보게 된다. 그때는 다시 처리하는 것 말고 방법이 없다 — 결과는 불변이라 열을
 * 나중에 덧붙일 수 없다.
 *
 * 막지는 않는다. 공칭만 필요한 작업도 정상이다. **처리 화면에서 미리 말할 뿐이다** —
 * 세 화면 건너에서 알게 되는 것과 여기서 아는 것은 되돌리는 비용이 다르다.
 */
export interface StepGap {
  plugin: string
  label: string
  lost: string
  /**
   * 이 단계가 **어느 축에** 걸려 있어야 하는가. `undefined` 면 축을 안 가린다.
   *
   * **id 만 보면 못 잡는 구멍이 있다.** 재샘플은 축마다 한 번씩 필요한데,
   * 공칭 축에 하나 있으면 `curve.resample` 이 「있다」 로 판정돼 진소성 축이
   * 비어도 아무 말 안 했다 — 그러면 카드로 내보낼 때 가서야 드러난다.
   */
  axis?: string
  /**
   * 이 축이 **있을 때만** 묻는다. 진소성 열을 안 만드는 구성에서 진소성 축의
   * 재샘플을 요구하면 그건 잔소리다.
   */
  onlyIf?: string
}

export const STEP_GAPS: StepGap[] = [
  {
    plugin: 'tensile.true_plastic',
    label: '진응력·진소성변형률',
    lost: '진응력 곡선과 CAE 카드(Abaqus·OpenRadioss)를 만들 수 없습니다',
  },
  {
    plugin: 'curve.resample',
    label: '균등 격자로 재샘플 (공칭 축)',
    lost: '여러 시편의 대표 곡선을 낼 수 없습니다 — 시편마다 x 격자가 달라 평균을 낼 자리가 없습니다',
    axis: 'strain_engineering',
  },
  {
    plugin: 'curve.resample',
    label: '균등 격자로 재샘플 (진소성 축)',
    lost:
      '진응력 곡선의 대표 곡선을 낼 수 없고, 덱에 싣는 표가 시편마다 다른 점에서 찍힙니다',
    axis: 'strain_true_plastic',
    onlyIf: 'tensile.true_plastic',
  },
]

/**
 * 이 구성에서 빠진 것. **단계를 통째로 받는다.**
 *
 * 이름 목록만 받는 길은 두지 않는다. 그 길이 있으면 축을 못 가리는 호출이 다시
 * 생기고, 그때 이 함수는 「있다」 고 답한다 — 없는 것을 있다고 말하는 쪽이
 * 아무 말도 안 하는 것보다 나쁘다.
 */
export function missingSteps(
  steps: readonly { plugin: string; options: Record<string, unknown> }[]
): StepGap[] {
  const present = new Set(steps.map((one) => one.plugin))
  return STEP_GAPS.filter((gap) => {
    if (!present.has(gap.plugin)) {
      // 그 축을 만들지도 않는 구성에 축별 경고를 띄우지 않는다 — 잔소리가 된다.
      return !gap.onlyIf || present.has(gap.onlyIf)
    }
    if (!gap.axis) return false
    if (gap.onlyIf && !present.has(gap.onlyIf)) return false
    return !steps.some((one) => one.plugin === gap.plugin && one.options.x === gap.axis)
  })
}
