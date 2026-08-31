/**
 * 시험 상세의 「뒤로」 가 어디로 가는가.
 *
 * ## 왜 화면이 스스로 못 정하나
 *
 * 시험 목록은 **부서 스코프**(`/w/:slug/tests`)라, 슬러그를 모르는 상세 화면은
 * 그 주소를 만들 수 없다. 그래서 **목록이 넘겨 준다**(`state.from`).
 *
 * ## 왜 늘 재료로 보내면 안 되나
 *
 * 전에는 무조건 재료 화면으로 갔다. 재료에서 들어온 사람에게는 맞지만, 목록에서
 * 20건을 훑는 중이던 사람은 **자리를 잃는다** — 돌아와서 다시 찾아 들어가야 한다.
 *
 * 반대로 주소를 직접 치고 들어왔을 때는 넘겨받은 것이 없다. 그때는 재료가 맞다 —
 * 재료 상세가 그 시험의 시편·형제 시험을 함께 갖고 있는 화면이다.
 */

export interface BackTarget {
  to: string
  label: string
}

/**
 * 이 시험이 붙은 **재료로 가는 길.** 재료를 모르면 `null`.
 *
 * `backTarget` 과 갈라 둔다. 「뒤로」 는 *왔던 자리*로 가므로 목록에서 들어온
 * 사람은 목록으로 돌아가는데, 그러면 **재료로 가는 길이 화면 어디에도 없다** —
 * 제목 밑에 재료 이름이 적혀 있을 뿐이라 읽을 수는 있고 갈 수는 없었다. 이것은
 * 왔던 자리와 무관하게 언제나 재료로 간다.
 */
export function materialTarget(
  item: { material_id?: string | null; material_name?: string | null } | null
): BackTarget | null {
  if (!item?.material_id) return null
  return { to: `/materials/${item.material_id}`, label: item.material_name ?? '재료' }
}

export function backTarget(
  from: BackTarget | undefined,
  item: { material_id?: string | null; material_name?: string | null } | null
): BackTarget {
  // **왔던 자리가 먼저다.** 넘겨받았다면 그것이 사람이 기대하는 곳이다.
  if (from) return from
  if (item?.material_id) {
    return { to: `/materials/${item.material_id}`, label: item.material_name ?? '재료' }
  }
  // 재료 카탈로그는 전사 화면이라 언제나 갈 수 있다.
  return { to: '/materials', label: '재료 목록' }
}
