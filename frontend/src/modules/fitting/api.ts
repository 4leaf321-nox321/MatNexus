/**
 * 적합·물성 카드 API.
 *
 * **미리보기는 저장하지 않는다.** 여러 식을 견줘 보는 것과 그중 하나를 골라 카드로
 * 남기는 것은 다른 일이다 — 견주는 동안 만들어진 카드가 쌓이면 어느 것이 결론인지
 * 알 수 없게 된다.
 */

import { api, downloadFile, downloadPostFile } from '@/shared/api/client'
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
export type ResampleMethod = components['schemas']['ResampleMethodOut']
export type BlockSpec = components['schemas']['BlockSpecOut']
export type Produced = components['schemas']['CardValueOut']
export type ViscoelasticCardSaveRequest =
  components['schemas']['ViscoelasticCardSaveRequest']
export type DeclaredCardSaveRequest = components['schemas']['DeclaredCardSaveRequest']
export type DeclaredCardPreview = components['schemas']['DeclaredCardPreviewOut']
export type CardPage = components['schemas']['Page_PropertyCardOut_']
/** 해석용 물성 정의 — **배포 없이 새 솔버**(ADR 0023). */
export type ExportProfile = components['schemas']['ExportProfileOut']
export type ExportProfileSave = components['schemas']['ExportProfileSaveRequest']
export type ExportProfileCreate = components['schemas']['ExportProfileCreateRequest']
export type DeckPreview = components['schemas']['DeckPreviewOut']
export type DeckScan = components['schemas']['DeckScanOut']
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

  /** 저장된 덱 정의. 내 부서 것 + 전역. */
  exportProfiles: () => api.get<ExportProfile[]>('/fitting/export-profiles'),
  createExportProfile: (payload: ExportProfileCreate) =>
    api.post<ExportProfile>('/fitting/export-profiles', payload),
  saveExportProfile: (key: string, payload: ExportProfileSave) =>
    api.put<ExportProfile>(`/fitting/export-profiles/${key}`, payload),
  removeExportProfile: (key: string) =>
    api.delete<void>(`/fitting/export-profiles/${key}`),

  /**
   * 예제 덱을 읽어 **정의 초안**을 만든다.
   *
   * 빈 폼에서 시작하면 막연하다 — 그런데 덱을 붙이려는 사람에게는 대개 그 솔버의
   * 덱 파일이 이미 있다. **구조는 서버가 읽고 「이 값이 무엇인가」 만 사람이 정한다**
   * (장비 파일 정의와 같은 선, ADR 0006).
   */
  scanDeck: (text: string, cardId?: string) =>
    api.post<DeckScan>('/fitting/export-profiles/scan', {
      text,
      card_id: cardId ?? null,
    }),

  /**
   * 저장하기 **전에** 실제 카드로 그려 본다.
   *
   * **못 냈어도 200 이다** — 못 낸 이유가 응답 안에 있다. 그래서 이것을 부르는
   * 화면은 `catch` 가 아니라 `error` 필드를 봐야 한다.
   */
  previewDeck: (definition: unknown, cardId: string, units = 'si') =>
    api.post<DeckPreview>('/fitting/export-profiles/preview', {
      definition,
      card_id: cardId,
      units,
    }),

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

  /**
   * 소성 표의 점을 다시 고르는 방법들. **화면이 적어 두지 않는다** — 새 방법이
   * 붙어도 이 파일은 안 고친다.
   */
  resampleMethods: () => api.get<ResampleMethod[]>('/fitting/resample-methods'),

  publish: (id: string) => api.post<PropertyCard>(`/fitting/cards/${id}/publish`, {}),

  /**
   * 사용 중지한 카드를 **초안으로** 되살린다. 부서 관리자만.
   *
   * 확정으로 바로 안 돌아가는 이유: 틀려서 중지한 카드가 확정 상태로 되살아나면
   * 그 값이 조용히 다시 쓰인다. 값은 그대로 살리되 「쓰겠다」 는 선언은 다시 받는다.
   */
  restore: (id: string) => api.post<PropertyCard>(`/fitting/cards/${id}/restore`, {}),

  /** 사용 중지 — **지우지 않는다.** 이 값으로 해석이 돌았을 수 있다. */
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

  /**
   * 고른 카드를 **한 묶음으로** 내려받는다 — 덱 + manifest + 체크섬(ADR 0024 ②).
   *
   * 해석 하나에 재료가 여럿 들어간다. 한 장씩 받아 사람이 폴더에 모으면 **그 묶음이
   * 무엇이었는지가 아무 데도 안 남는다** — 해석자가 「내가 받은 이 덱이 그때 그
   * 카드가 맞나」 를 물을 때 답할 것이 없다.
   */
  downloadBundle: (ids: string[], format: ExportFormat, system: UnitSystem) =>
    downloadPostFile(
      '/fitting/cards/bundle',
      { card_ids: ids, format: format.key, units: system.key },
      // 서버도 같은 이름을 붙인다. 낱장 내보내기와 같은 규약이라 여기서도 적는다.
      `matnexus_cards_${format.key}_${system.key}.zip`
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
  // 「내림」 이었다. **무엇을 내린다는 것인지 안 읽힌다** — 게시물을 내리는 것과
  // 헷갈리고, 지운다는 뜻으로도 읽힌다. 이 상태의 뜻은 하나다: 앞으로 쓰지 않는다.
  deprecated: '사용 중지',
}
