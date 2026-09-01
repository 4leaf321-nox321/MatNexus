/**
 * 인장시험의 **표준 처리 단계**.
 *
 * ## 왜 기본을 두는가
 *
 * 새 레시피는 빈 목록에서 시작한다. 그래서 사람들은 필요한 것만 골라 담고,
 * 대개 `공칭 → 정렬 → 강도` 셋에서 멈춘다. 그 구성은 화면에서 잘 돌아 보이는데
 * **CAE 카드도 대표 곡선도 못 만든다** — 그 사실은 세 화면 건너에서야 드러나고,
 * 그때는 다시 처리하는 것 말고 방법이 없다(결과는 불변이다).
 *
 * `gaps.ts` 가 「이게 빠졌습니다」 를 말하고 있었지만, **말하는 것과 넣어 주는
 * 것은 다르다.** 무엇을 어느 자리에 어떤 옵션으로 넣어야 하는지가 또 하나의
 * 문제여서, 알고도 못 하는 사람이 있었다.
 *
 * ## 순서가 곧 규칙이다
 *
 * 이 목록의 순서에는 이유가 있다.
 *
 *   1. 공칭 — 변위·하중을 응력·변형률로. 시편 치수가 여기서 들어온다.
 *   2. 정렬 — 보간과 교점 계산이 정렬을 전제한다.
 *   3. 재샘플 — **여러 시편의 평균을 내려면 x 격자가 같아야 한다.**
 *   4. 강도 — 인장강도와 그 자리.
 *   5. 탄성계수 — 항복강도와 진소성이 이 값을 쓴다.
 *   6. 항복강도 — 0.2% 오프셋.
 *   7. 네킹 후보 — 어디서 잘라야 하는지 짚는다.
 *   8. 자르기 — **네킹을 지나면 진소성변형률이 되돌아온다.** 안 자르면 그
 *      뒤가 단조 증가가 아니라 재샘플도 적합도 못 한다.
 *   9. 진응력·진소성 — 경화식이 쓰는 축.
 *  10. 정렬 — 진소성 축은 공칭 축과 순서가 다를 수 있다.
 *  11. 재샘플 — 진소성 축도 격자를 맞춰야 한다.
 *
 * ## 채우지 못하는 칸이 하나 있다
 *
 * 재샘플의 **끝 값**은 여기서 정할 수 없다. 묶음의 모든 시편이 **같은 값**이어야
 * 하는데, 그 값은 가장 짧은 곡선이 정하고 그것은 재료마다 다르다. 지어내면
 * 어떤 재료에서는 데이터를 잘라 버린다.
 *
 * 비워 두면 관측 최댓값이 쓰이고 시편마다 달라진다 — 통계가 그때 어느 값으로
 * 고정하면 되는지 문장으로 말해 준다. **모르는 것을 지어내지 않는다.**
 */

import type { RecipeStep } from '@/modules/processing/api'

/** 인장 표준 단계. 순서가 규칙이다 — 위 주석을 본다. */
export const TENSILE_STANDARD: RecipeStep[] = [
  {
    plugin: 'tensile.engineering',
    // 시편 치수는 곡선에 없다. `@` 가 그 다리를 놓는다.
    options: { gauge_length: '@specimen_gauge_length', area: '@specimen_area' },
  },
  {
    plugin: 'curve.sort_unique',
    options: { x: 'strain_engineering', duplicate_policy: 'mean' },
  },
  {
    plugin: 'curve.resample',
    // 끝은 비워 둔다 — 묶음이 정하는 값이라 여기서는 알 수 없다.
    options: { x: 'strain_engineering', count: 400, start: 0 },
  },
  { plugin: 'tensile.strength', options: {} },
  { plugin: 'tensile.elastic_modulus', options: { method: 'auto' } },
  {
    plugin: 'tensile.proof_stress',
    options: { offset_strain: 0.002, youngs_modulus: '@youngs_modulus' },
  },
  { plugin: 'tensile.necking_candidate', options: {} },
  {
    plugin: 'curve.crop',
    options: { x: 'strain_engineering', end: '@necking_candidate_strain' },
  },
  { plugin: 'tensile.true_plastic', options: { youngs_modulus: '@youngs_modulus' } },
  // **여기만 '마지막 점만 남김' 이다.** `clip_zero` 가 탄성 구간을 전부 x=0 에
  // 쌓아 두는데(실측 120점 중 34점), 그것을 평균 내면 x=0 의 응력이 탄성 구간
  // 전체의 평균이 된다 — 항복응력이 아니라 그보다 한참 낮은 값이고, 경화식의
  // 첫 점이 그 값이면 적합이 통째로 아래로 끌려간다. 마지막 점이 항복점이다.
  {
    plugin: 'curve.sort_unique',
    options: { x: 'strain_true_plastic', duplicate_policy: 'last' },
  },
  {
    plugin: 'curve.resample',
    options: { x: 'strain_true_plastic', count: 300, start: 0 },
  },
]

/**
 * 지금 목록에 **빠진 표준 단계만** 골라 순서대로 돌려준다.
 *
 * 통째로 갈아 끼우지 않는다 — 사람이 손댄 옵션(적합 구간·오프셋)을 말없이
 * 되돌리면, 그 사람은 자기가 정한 값이 사라진 것을 나중에 결과에서 안다.
 */
export function missingStandard(plugins: string[]): RecipeStep[] {
  const have = new Set(plugins)
  return TENSILE_STANDARD.filter((step) => !have.has(step.plugin)).map((step) => ({
    plugin: step.plugin,
    options: { ...step.options },
  }))
}


/**
 * 처음 열었을 때 깔리는 순서 — **바로 돌려 볼 수 있는 것.**
 *
 * **표준(`TENSILE_STANDARD`)의 복사본이다.** 두 목록을 따로 적어 두면 한쪽만
 * 고쳐지고, 그때 화면은 「처음 깔리는 것」 과 「빠진 것 채우기」 가 서로 다른
 * 차례를 가르친다. 이름을 둘 두는 것은 **쓰는 자리가 다르기 때문**이다 —
 * 이쪽은 새 레시피에 깔리고, 저쪽은 이미 있는 목록과 대조된다.
 *
 * 복사본인 이유는 부르는 쪽이 옵션을 채워 넣기 때문이다(`defaults`). 같은
 * 배열을 나눠 쓰면 그 손질이 표준까지 물들인다.
 *
 * ## 다듬기를 뺐다가 도로 넣었다
 *
 * 전에는 정렬·재샘플을 뺐다 — 「다듬기는 나중」 이라는 생각이었다. 그런데
 * **처음 여는 사람이 실제로 돌리는 것이 이 구성**이고, 재샘플이 없으면 그
 * 결과로는 재료의 대표 곡선이 영영 안 나온다. 그 사실은 재료 물성 화면에서야
 * 드러나고, 그때는 다시 처리하는 것 말고 방법이 없다(결과는 불변이다).
 * 실측 2026-08-31: 이 구성으로 처리한 인장 6건이 18점·718점으로 갈려 대표
 * 곡선이 안 나왔다.
 *
 * **공칭 축을 넣고 나니 진소성 축을 뺄 근거가 없어졌다.** 「끝을 정할 값이
 * 없다」 는 두 축에 똑같이 해당하고(공칭은 관측 최댓값, 진소성은 네킹 자르기),
 * 그건 *넣지 말 이유*가 아니라 *첫 판에 격자가 안 맞는 이유*다 — 통계가 공통
 * 구간을 계산해 말해 주고, 두 번째 판에서 고정한다. 게다가 진소성 축은
 * **덱이 실제로 싣는 축**이라 여기서 빠지면 목적지에서 걸린다.
 *
 * 넣어도 잃는 것이 없다. 재샘플은 맨 뒤에 돌고(`order=95`), 탄성계수·항복강도는
 * 그 전에 **잰 점**으로 계산된다.

 * 빼면 안 되는 것이 진응력이다. 솔버 덱이 요구하는 것은 공칭이 아니라
 * 진응력-진소성변형률이라(`matcore/export`), 여기서 끊으면 채택해도 결과 화면이
 * 「채택된 결과에 진응력 열이 없습니다」 로 되돌려 보낸다.
 */
export const DMA_STARTER: RecipeStep[] = [
  { plugin: 'dma.derived', options: {} },
  { plugin: 'curve.sort_unique', options: { x: 'temperature', duplicate_policy: 'mean' } },
]

export const TENSILE_STARTER: RecipeStep[] = TENSILE_STANDARD.map((step) => ({
  plugin: step.plugin,
  options: { ...step.options },
}))
