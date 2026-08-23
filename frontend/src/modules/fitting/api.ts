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
export type PropertyCardSaveRequest = components['schemas']['PropertyCardSaveRequest']
type PropertyCardUpdate = components['schemas']['PropertyCardUpdateRequest']
export type ExportFormat = components['schemas']['ExportFormatOut']
export type BlockSpec = components['schemas']['BlockSpecOut']
export type Produced = components['schemas']['CardValueOut']
export type ViscoelasticCardSaveRequest =
  components['schemas']['ViscoelasticCardSaveRequest']

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

  cards: (materialId?: string) =>
    api.get<PropertyCard[]>(
      `/fitting/cards${materialId ? `?material_id=${materialId}` : ''}`
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
  download: (id: string, format: ExportFormat, label: string) =>
    downloadFile(
      `/fitting/cards/${id}/export?format=${format.key}`,
      `${filename(label)}.${format.extension}`
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
