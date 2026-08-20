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

export const vocabularyApi = {
  /** 축 목록. 화면이 '새로 추가' 를 보여 줄지 정하는 데 쓴다. */
  list: () => api.get<Vocabulary[]>('/vocabularies'),

  /**
   * 값 검색. **별칭으로도 찾힌다** — `'포스코(주)'` 를 치면 `'포스코'` 가 온다.
   * 그래서 받은 결과를 화면이 다시 거르면 안 된다.
   */
  search: (slug: string, q: string) =>
    api.get<Term[]>(`/vocabularies/${slug}/terms${q ? `?q=${encodeURIComponent(q)}` : ''}`),

  /**
   * 값 추가. **이미 있으면 그것이 돌아온다** — 409 가 아니다.
   *
   * 피커는 사람이 엔터를 치는 순간 낙관적으로 보낸다. 그때 오류를 그리게 하면,
   * 실제로 일어난 일이 "이미 있는 값을 골랐다" 뿐인데도 화면이 멈춘다.
   */
  create: (slug: string, value: string) =>
    api.post<Term>(`/vocabularies/${slug}/terms`, { value }),
}
