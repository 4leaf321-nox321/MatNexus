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
}

export const STEP_GAPS: StepGap[] = [
  {
    plugin: 'tensile.true_plastic',
    label: '진응력·진소성변형률',
    lost: '진응력 곡선과 CAE 카드(Abaqus·OpenRadioss)를 만들 수 없습니다',
  },
  {
    plugin: 'curve.resample',
    label: '균등 격자로 재샘플',
    lost: '여러 시편의 대표 곡선을 낼 수 없습니다 — 시편마다 x 격자가 달라 평균을 낼 자리가 없습니다',
  },
]

export function missingSteps(plugins: string[]): StepGap[] {
  const present = new Set(plugins)
  return STEP_GAPS.filter((gap) => !present.has(gap.plugin))
}
