/**
 * 재료 상세의 탭 — **주소에 실리는 이름이라 곧 계약이다.**
 *
 * 다른 화면이 「그 재료의 CAE 카드로」 처럼 탭을 지목해 보낸다(워크벤치의 단계 안내,
 * 홈의 남은 일). 주소에 안 담으면 링크가 늘 첫 탭으로 떨어지고, 사람은 안내가 말한
 * 자리를 스스로 찾아야 한다 — 그런 안내는 없느니만 못하다.
 *
 * 모르는 값은 첫 탭으로 돌린다. 탭 이름을 바꿔 옛 링크·즐겨찾기가 남아 있을 때
 * **빈 화면을 보이는 대신** 뭐라도 보여 준다.
 */

export const TABS = ['samples', 'properties', 'cards'] as const

export type MaterialTab = (typeof TABS)[number]

export function tabOf(asked: string | null | undefined): MaterialTab {
  return TABS.includes(asked as MaterialTab) ? (asked as MaterialTab) : 'samples'
}
