/**
 * 어휘 API — **피커가 쓰는 것.**
 *
 * 전체를 받지 않는다. 어휘가 수만 개가 되면(ADR 0010) 브라우저로 다 보낼 수
 * 없고, 보내 봐야 화면은 60개만 그린다. 검색어를 보내고 서버가 상한을 건다.
 *
 * `OptionPicker` 의 `search` 에 그대로 물린다 — 그쪽은 도메인을 모르고, 여기는
 * 화면을 모른다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Vocabulary = components['schemas']['VocabularyOut']
export type Term = components['schemas']['TermOut']
type TermUpdate = components['schemas']['TermUpdateRequest']

export const vocabularyApi = {
  /** 축 목록. 화면이 '새로 추가' 를 보여 줄지 정하는 데 쓴다. */
  list: () => api.get<Vocabulary[]>('/vocabularies'),

  /**
   * 값 검색. **별칭으로도 찾힌다** — `'포스코(주)'` 를 치면 `'포스코'` 가 온다.
   * 그래서 받은 결과를 화면이 다시 거르면 안 된다.
   */
  search: (
    slug: string,
    q: string,
    options: { includeHidden?: boolean; leastUsed?: boolean; parentValue?: string } = {}
  ) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (options.includeHidden) params.set('include_hidden', 'true')
    // 오타는 늘 `쓰는 곳 1` 로 생긴다 — 기본 정렬에서는 목록 끝에 묻힌다.
    if (options.leastUsed) params.set('least_used', 'true')
    // **상위 축으로 좁힌다.** Steel 을 골랐으면 강종 후보가 그 아래로 줄어야
    // 한다 — 강종이 수만 개일 때 이것이 규모에서 가장 큰 이득이다.
    if (options.parentValue) params.set('parent_value', options.parentValue)
    const query = params.toString()
    return api.get<Term[]>(`/vocabularies/${slug}/terms${query ? `?${query}` : ''}`)
  },

  /**
   * 표기를 고치거나 감춘다. **관리자만.**
   *
   * 이름을 고치면 그 값을 가리키던 것이 전부 따라온다 — 외래키라서 그렇다.
   * 지우는 길은 없다. 지우면 그것을 쓰던 시료가 무엇이었는지 알 수 없게 된다.
   */
  update: (slug: string, id: string, body: TermUpdate) =>
    api.patch<Term>(`/vocabularies/${slug}/terms/${id}`, body),

  /**
   * `쓰는 곳` 다시 세기. **캐시가 어긋났을 때.**
   *
   * 평소에는 참조가 바뀌는 지점에서 증감한다 — 화면을 열 때마다 전체를 세지
   * 않으려고. 그 지점을 하나 빠뜨리면 조용히 벌어지므로 고칠 길을 둔다.
   */
  recount: (slug: string) => api.post<Term[]>(`/vocabularies/${slug}/recount`, {}),

  /**
   * 값 추가. **이미 있으면 그것이 돌아온다** — 409 가 아니다.
   *
   * 피커는 사람이 엔터를 치는 순간 낙관적으로 보낸다. 그때 오류를 그리게 하면,
   * 실제로 일어난 일이 "이미 있는 값을 골랐다" 뿐인데도 화면이 멈춘다.
   */
  create: (slug: string, value: string, parentValue?: string) =>
    api.post<Term>(`/vocabularies/${slug}/terms`, {
      value,
      // 새 값이 부모를 물려받는다 — 계층이 쓰면서 저절로 만들어진다.
      parent_value: parentValue ?? null,
    }),
}
