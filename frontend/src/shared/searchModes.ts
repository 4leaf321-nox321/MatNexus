/**
 * 찾는 방식과 「왜 걸렸나」 의 말 — **전체 검색과 목록 찾기 상자가 같은 말을 쓴다**(2026-09-29).
 *
 * 전체 검색 화면(`modules/search/SearchPage`)에만 세 방식이 있고, 매일 쓰는 재료·시험 목록의
 * 찾기 상자는 「포함」 하나였다. 오타 하나면 0건이었다. 이제 셋 다 같은 셋을 쓴다 — 화면마다
 * 말이 다르면 「비슷」 이 어디서는 뜻까지 보고 어디서는 안 보는지 사람이 외워야 한다.
 *
 *     일치     정확히 그 이름
 *     포함     그 말이 들어간 것 (기본)
 *     비슷     오타·표기 흔들림, 뜻이 가까운 것까지 — 가까운 순으로 선다
 *
 * 그리는 것은 `shared/components/SearchMode` 에 있다(단추·배지). 여기는 표만 둔다.
 */

export const SEARCH_MODES = [
  { key: 'exact', label: '일치', hint: '정확히 그 이름' },
  { key: 'contains', label: '포함', hint: '그 말이 들어간 것' },
  { key: 'similar', label: '비슷', hint: '오타·표기 흔들림, 뜻이 가까운 것까지' },
] as const

export type SearchMode = (typeof SEARCH_MODES)[number]['key']

export function isSearchMode(value: string | null | undefined): value is SearchMode {
  return SEARCH_MODES.some((one) => one.key === value)
}

/** 서버의 `matched` → 사람 말. 전체 검색 결과와 목록 배지가 같은 표를 읽는다. */
export const MATCH_LABELS: Record<string, string> = {
  exact: '정확히 일치',
  prefix: '앞이 일치',
  contains: '포함',
  similar: '비슷함',
  // 글자는 안 겹치는데 뜻이 가깝다. **이 표시가 없으면 엉뚱한 결과로 읽힌다.**
  meaning: '뜻이 가까움',
  both: '글자·뜻 둘 다',
}
