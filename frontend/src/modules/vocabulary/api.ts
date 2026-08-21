/**
 * 기준정보 API — **피커가 쓰는 것.**
 *
 * 전체를 받지 않는다. 기준정보가 수만 개가 되면(ADR 0010) 브라우저로 다 보낼 수
 * 없고, 보내 봐야 화면은 60개만 그린다. 검색어를 보내고 서버가 상한을 건다.
 *
 * `OptionPicker` 의 `search` 에 그대로 물린다 — 그쪽은 도메인을 모르고, 여기는
 * 화면을 모른다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Vocabulary = components['schemas']['VocabularyOut']
export type Term = components['schemas']['TermOut']
export type Alias = components['schemas']['TermAliasOut']
/**
 * 시편 규격이 갖는 치수 칸 하나. **시험 종류가 선언한다.**
 *
 * 목록을 화면에 적지 않는다 — 시험 종류를 추가할 때 두 곳을 고쳐야 하고, 그러면
 * 한 곳을 빠뜨린다(처리 단계의 `ParamSpec` 과 같은 자리, D7).
 */
export type SpecimenField = components['schemas']['SpecimenFieldOut']
/** 값이 고를 수 있는 종류. 키가 아니라 이름을 함께 준다. */
export type TermKind = components['schemas']['TermKindOut']
export type BulkResult = components['schemas']['BulkTermOut']
export type DeleteResult = components['schemas']['BulkDeleteOut']
export type DriftReport = components['schemas']['DriftReportOut']
type TermPage = components['schemas']['Page_TermOut_']

/** 한 번에 보낼 수 있는 최대 줄 수. **서버가 같은 수를 강제한다.** */
export const BULK_MAX = 500
type TermUpdate = components['schemas']['TermUpdateRequest']

export const vocabularyApi = {
  /**
   * 축 목록. 화면이 '새로 추가' 를 보여 줄지, **치수 칸을 그릴지** 정하는 데 쓴다
   * (`attribute_source`).
   */
  list: () => api.get<Vocabulary[]>('/vocabularies'),

  /**
   * 이 시험 종류의 규격이 갖는 치수 칸. **화면이 이걸로 입력 폼을 그린다.**
   *
   * 인장 규격에는 어깨 반경이 있고 DMA 규격에는 지지 간격이 있다 — 하나의
   * 고정된 칸 목록으로 둘을 담으면 절반이 늘 비고, 그 빈 칸이 "안 쟀다" 인지
   * "이 규격에 없는 값" 인지 구별되지 않는다.
   */
  /** 이 축의 값이 고를 수 있는 종류. **치수 칸을 선언한 시험 종류만.** */
  kinds: (slug: string) => api.get<TermKind[]>(`/vocabularies/${slug}/kinds`),

  specimenFields: (slug: string, kind: string) =>
    api.get<SpecimenField[]>(
      `/vocabularies/${slug}/specimen-fields?kind=${encodeURIComponent(kind)}`
    ),

  /**
   * 문자열 컬럼과 기준정보가 어긋난 행. **0 이어야 한다.**
   *
   * 지금은 같은 사실을 두 벌로 들고 있다(ADR 0010 Expand) — `materials.family`
   * 문자열과 `family_term_id`. 문자열을 지우기 전에 두 벌이 같다는 것을 한
   * 릴리스 동안 봐야 하고, 볼 도구가 없으면 "지켜봤다" 가 말이 안 된다.
   */
  drift: () => api.get<DriftReport>('/vocabularies/drift'),

  /**
   * 지금 다시 잰다. **읽기와 가른다** — 화면을 열 때마다 새로 재면 이력이
   * 사람이 창을 연 횟수가 된다. 게이트가 묻는 것은 "저절로 돌 때도 계속 0
   * 이었나" 이므로 그 이력이 더러우면 안 된다.
   */
  measureDrift: () => api.post<DriftReport>('/vocabularies/drift', {}),

  /**
   * 어긋난 칸을 바로잡는다. **기준정보가 정본이다.**
   *
   * 자동으로 안 돈다 — 방향을 정해야 하는 일이라 사람이 점검을 보고 누른다.
   * 고치기 전의 목록이 돌아온다.
   */
  repair: () => api.post<DriftReport>('/vocabularies/repair', {}),

  /**
   * 값 검색. **별칭으로도 찾힌다** — `'포스코(주)'` 를 치면 `'포스코'` 가 온다.
   * 그래서 받은 결과를 화면이 다시 거르면 안 된다.
   */
  search: (
    slug: string,
    q: string,
    options: {
      includeHidden?: boolean
      leastUsed?: boolean
      parentValue?: string
      limit?: number
      offset?: number
    } = {}
  ) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (options.includeHidden) params.set('include_hidden', 'true')
    // 오타는 늘 `쓰는 곳 1` 로 생긴다 — 기본 정렬에서는 목록 끝에 묻힌다.
    if (options.leastUsed) params.set('least_used', 'true')
    // **상위 축으로 좁힌다.** Steel 을 골랐으면 강종 후보가 그 아래로 줄어야
    // 한다 — 강종이 수만 개일 때 이것이 규모에서 가장 큰 이득이다.
    if (options.parentValue) params.set('parent_value', options.parentValue)
    if (options.limit !== undefined) params.set('limit', String(options.limit))
    if (options.offset) params.set('offset', String(options.offset))
    const query = params.toString()
    return api.get<TermPage>(`/vocabularies/${slug}/terms${query ? `?${query}` : ''}`)
  },

  /**
   * 고른 값들을 지운다. **못 지운 것은 이유가 온다.**
   *
   * 쓰이고 있는 값은 안 지운다 — 지우면서 참조를 끊으면 그 시료가 어느
   * 제조사였는지 영영 알 수 없게 된다. 그럴 때는 감추기나 병합을 쓴다.
   */
  removeMany: (slug: string, ids: string[]) =>
    api.post<DeleteResult>(`/vocabularies/${slug}/terms/delete`, { ids }),

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
   * 여러 값을 한 번에. **건별로 결과가 온다.**
   *
   * 개수만 보면 "50개 중 12개가 새로 생겼습니다" 로 끝나는데, 알고 싶은 것은
   * 어느 것이 안 생겼고 왜인지다 — 특히 친 것과 다른 값에 붙은 경우.
   */
  createBulk: (slug: string, values: string[], parentValue?: string) =>
    api.post<BulkResult>(`/vocabularies/${slug}/terms/bulk`, {
      values,
      parent_value: parentValue ?? null,
    }),

  /** 이 값의 다른 표기들. */
  aliases: (slug: string, termId: string) =>
    api.get<Alias[]>(`/vocabularies/${slug}/terms/${termId}/aliases`),

  /**
   * 다른 표기를 잇는다. **사후 병합보다 싸다** — 등록해 두면 값을 만들 때
   * 게이트가 별칭까지 뒤져서 애초에 중복이 안 생긴다.
   */
  addAlias: (slug: string, termId: string, alias: string) =>
    api.post<Alias>(`/vocabularies/${slug}/terms/${termId}/aliases`, { alias }),

  removeAlias: (slug: string, termId: string, aliasId: string) =>
    api.delete<void>(`/vocabularies/${slug}/terms/${termId}/aliases/${aliasId}`),

  /** 합칠 만한 값 묶음. **탐지만 한다** — 합치는 것은 사람이 누른다. */
  mergeCandidates: (slug: string) =>
    api.get<Term[][]>(`/vocabularies/${slug}/merge-candidates`),

  /**
   * 이 값을 다른 값으로 합친다. **없어진 표기는 별칭으로 남는다** — 다음에 누가
   * 옛 표기를 쳐도 자동으로 흡수된다.
   */
  merge: (slug: string, termId: string, intoId: string) =>
    api.post<Term>(`/vocabularies/${slug}/terms/${termId}/merge`, { into_id: intoId }),

  /** "이 둘은 다른 값이다" 를 기억한다 — 안 기억하면 매번 다시 묻는다. */
  dismiss: (slug: string, firstId: string, secondId: string) =>
    api.post<void>(`/vocabularies/${slug}/dismissals`, {
      first_id: firstId,
      second_id: secondId,
    }),

  /**
   * 값 추가. **이미 있으면 그것이 돌아온다** — 409 가 아니다.
   *
   * 피커는 사람이 엔터를 치는 순간 낙관적으로 보낸다. 그때 오류를 그리게 하면,
   * 실제로 일어난 일이 "이미 있는 값을 골랐다" 뿐인데도 화면이 멈춘다.
   */
  create: (
    slug: string,
    value: string,
    parentValue?: string,
    /** 속성을 갖는 축(시편 규격)에서만. 값은 **SI 로 보낸다.** */
    extra?: { kind?: string | null; attributes?: Record<string, number> }
  ) =>
    api.post<Term>(`/vocabularies/${slug}/terms`, {
      value,
      // 새 값이 부모를 물려받는다 — 계층이 쓰면서 저절로 만들어진다.
      parent_value: parentValue ?? null,
      ...(extra ?? {}),
    }),
}
