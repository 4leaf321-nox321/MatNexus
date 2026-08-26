/**
 * 적합·물성 카드 API.
 *
 * **미리보기는 저장하지 않는다.** 여러 식을 견줘 보는 것과 그중 하나를 골라 카드로
 * 남기는 것은 다른 일이다 — 견주는 동안 만들어진 카드가 쌓이면 어느 것이 결론인지
 * 알 수 없게 된다.
 */

import { api, downloadFile } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Family = components['schemas']['FamilyOut']
export type Fit = components['schemas']['FitOut']
export type FitPreview = components['schemas']['FitPreviewOut']
export type FitPreviewRequest = components['schemas']['FitPreviewRequest']
export type InheritedValue = components['schemas']['InheritedValueOut']
export type FittedParameter = components['schemas']['FittedParameterOut']
export type PropertyCard = components['schemas']['PropertyCardOut']
/** 덱을 쓸 단위계. **목록은 서버가 준다** — 화면이 적어 두면 계가 늘 때 뒤처진다. */
export type UnitSystem = components['schemas']['UnitSystemOut']
export type PropertyCardSaveRequest = components['schemas']['PropertyCardSaveRequest']
type PropertyCardUpdate = components['schemas']['PropertyCardUpdateRequest']
export type ExportFormat = components['schemas']['ExportFormatOut']
export type BlockSpec = components['schemas']['BlockSpecOut']
export type Produced = components['schemas']['CardValueOut']
export type ViscoelasticCardSaveRequest =
  components['schemas']['ViscoelasticCardSaveRequest']
export type DeclaredCardSaveRequest = components['schemas']['DeclaredCardSaveRequest']
export type DeclaredCardPreview = components['schemas']['DeclaredCardPreviewOut']
export type CardPage = components['schemas']['Page_PropertyCardOut_']
/** 거를 수 있는 값들과 **각각 몇 장인가.** 개수는 서버가 센다. */
export type CardFacets = components['schemas']['CardFacetsOut']

/**
 * 카드 목록을 좁히는 축.
 *
 * **거르는 일은 서버가 한다.** 앞 50장만 받아 화면에서 거르면 뒤엣것이 없는
 * 카드가 된다 — 재료 목록 패널이 같은 이유로 그렇게 되어 있다.
 */
export interface CardQuery {
  material_id?: string
  status?: string
  /** 시험종류 key. **`none` 은 시험 없이 만든 카드**다(ADR 0016). */
  test_type_key?: string
  /** 부서 id. `global` 은 전역 재료의 카드. */
  owner?: string
  q?: string
  limit?: number
  offset?: number
}

/** 시험 없이 만든 카드를 가리키는 값. 서버의 `NO_TEST` 와 같다. */
export const NO_TEST = 'none'
/** 전역 재료를 가리키는 값. 서버의 `GLOBAL_OWNER` 와 같다. */
export const GLOBAL_OWNER = 'global'

function search(query: CardQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export const fittingApi = {
  families: () => api.get<Family[]>('/fitting/families'),

  /**
   * 물성 블록 선언. **화면이 이것만으로 카드를 그린다.**
   *
   * 화면이 `elastic`·`viscoelastic` 같은 이름을 하나도 모른다 — 그것이 새 물성을
   * 더하는 값을 마이그레이션 0·화면 0 으로 만드는 자리다(D7).
   */
  blocks: () => api.get<BlockSpec[]>('/fitting/blocks'),

  /** 저장하지 않고 견줘 본다. `families` 를 비우면 등록된 식 전부. */
  preview: (body: FitPreviewRequest) => api.post<FitPreview>('/fitting/preview', body),

  /**
   * 물성 카드 목록. **쪽으로 온다** — `total` 이 함께 오므로 화면이 "다음 쪽이
   * 있나" 를 알려고 한 건 더 요청하는 편법을 안 쓴다.
   */
  cards: (query: CardQuery = {}) => api.get<CardPage>(`/fitting/cards${search(query)}`),

  /**
   * 거를 수 있는 값들과 각각 몇 장인가.
   *
   * **화면이 한 페이지에서 세면 안 된다.** 50장만 받아 세면 「인장시험 12」라고
   * 적히는데 실제로는 40장일 수 있고, 그러면 필터 옆의 숫자가 거짓말을 한다.
   */
  cardFacets: (materialId?: string) =>
    api.get<CardFacets>(
      `/fitting/cards/facets${materialId ? `?material_id=${materialId}` : ''}`
    ),

  card: (id: string) => api.get<PropertyCard>(`/fitting/cards/${id}`),

  create: (body: PropertyCardSaveRequest) =>
    api.post<PropertyCard>('/fitting/cards', body),

  /**
   * Prony 적합에서 점탄성 카드를 만든다.
   *
   * **묶음을 받지 않는다.** 경화 카드는 재료+시험종류+방향의 대표 곡선에서
   * 나오지만 Prony 는 마스터커브 하나에 매달려 있다 — 재료·방향은 서버가 체인을
   * 따라 찾는다.
   */
  createViscoelastic: (body: ViscoelasticCardSaveRequest) =>
    api.post<PropertyCard>('/fitting/cards/viscoelastic', body),

  /**
   * **시험 없이** 적어 둔 값만으로 카드를 만든다(ADR 0016).
   *
   * `create` 는 대표 곡선에서 시작하므로 시험이 하나도 없는 재료는 탈 수 없다.
   * 그런데 탄성계수·열물성은 인장시험이 주지 않는 값이라, 그것만으로도 열해석·
   * 선형 정적 해석의 덱은 나간다.
   */
  createDeclaredCard: (body: DeclaredCardSaveRequest) =>
    api.post<PropertyCard>('/fitting/cards/declared', body),

  /**
   * 그 카드에 **무엇이 실리는지.** 만들기 전에 묻는다.
   *
   * 화면이 재료 API 를 따로 불러 나름대로 판정하지 않는다 — 규칙이 두 벌이
   * 되면 어긋나는 순간 화면이 거짓말을 한다. 카드를 만들 때 실제로 쓰는
   * 계산과 **같은 코드**가 이 답을 낸다.
   */
  declaredPreview: (materialId: string) =>
    api.get<DeclaredCardPreview>(
      `/fitting/cards/declared/preview?material_id=${materialId}`
    ),

  /** 확정 — 부서 관리자만. 올린 뒤에는 값을 바꿀 수 없다. */
  /**
   * 이름·메모만 고친다. **초안일 때만.**
   *
   * 값은 못 바꾼다 — 그래야 "이 카드가 무엇으로 나왔나" 에 항상 답할 수 있다.
   * 다만 오타 하나에 카드를 지우고 적합을 다시 돌리게 할 이유는 없다.
   */
  update: (id: string, body: PropertyCardUpdate) =>
    api.patch<PropertyCard>(`/fitting/cards/${id}`, body),

  publish: (id: string) => api.post<PropertyCard>(`/fitting/cards/${id}/publish`, {}),

  /** 내리기 — **지우지 않는다.** 이 값으로 해석이 돌았을 수 있다. */
  deprecate: (id: string) => api.post<PropertyCard>(`/fitting/cards/${id}/deprecate`, {}),

  /** 초안만 지울 수 있다. */
  remove: (id: string) => api.delete<void>(`/fitting/cards/${id}`),

  /** 솔버 목록. **화면이 손으로 적지 않는다** — 새 솔버가 붙으면 따라온다. */
  formats: () => api.get<ExportFormat[]>('/fitting/formats'),

  /**
   * 솔버 카드를 내려받는다.
   *
   * `<a href>` 로는 안 된다 — access 토큰이 메모리에만 있어 브라우저가 스스로
   * 여는 링크에는 실리지 않고, 401 이 새 탭에서 나므로 화면에 아무 표시도 안 뜬다.
   */
  unitSystems: () => api.get<UnitSystem[]>('/fitting/unit-systems'),

  /**
   * 덱을 내려받는다. **파일 이름에 단위계를 적는다.**
   *
   * 두 계가 한 폴더에 섞이면 어느 쪽이 어느 계인지 파일을 열어야 알게 되고,
   * 그때 안 열어 보는 사람이 생긴다 — 단위계가 섞인 덱은 조용히 1000배 틀린
   * 답을 낸다. 서버도 같은 이름을 붙이지만 이 함수가 이름을 정하므로 여기서도
   * 적어야 한다.
   */
  download: (id: string, format: ExportFormat, label: string, system: UnitSystem) =>
    downloadFile(
      `/fitting/cards/${id}/export?format=${format.key}&units=${system.key}`,
      `${filename(label)}_${system.key}.${format.extension}`
    ),
}

/** 파일 이름으로 쓸 수 있게 다듬는다. 한글은 남긴다 — 사람이 찾는 이름이다. */
export function filename(label: string): string {
  return label.replace(/[^\w가-힣.-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '') || 'card'
}

/** 카드 상태의 한국어 이름과 뜻. */
export const STATUS_LABELS: Record<string, string> = {
  draft: '초안',
  published: '확정',
  deprecated: '내림',
}
