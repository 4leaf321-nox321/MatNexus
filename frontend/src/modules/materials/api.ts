/** 재료·시료·시편 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Material = components['schemas']['MaterialOut']
export type MaterialPage = components['schemas']['Page_MaterialOut_']
export type Sample = components['schemas']['SampleOut']
export type Specimen = components['schemas']['SpecimenOut']
export type NamePreview = components['schemas']['NamePreviewOut']
export type Classification = components['schemas']['ClassificationOut']

type MaterialCreate = components['schemas']['MaterialCreateRequest']
type MaterialUpdate = components['schemas']['MaterialUpdateRequest']
type SpecimenUpdate = components['schemas']['SpecimenUpdateRequest']
type SampleCreate = components['schemas']['SampleCreateRequest']
type SpecimenCreate = components['schemas']['SpecimenCreateRequest']
type NamePreviewRequest = components['schemas']['NamePreviewRequest']

/**
 * 화면이 쓰는 단위. 값과 함께 **항상 명시해서 보낸다** — 서버가 SI 로 바꿔 저장하고
 * 무엇으로 입력받았는지 기록한다. 생략 가능하게 두면 "이 값이 mm 였나 m 였나"를
 * 나중에 아무도 답할 수 없다.
 */
export type PropertySources = components['schemas']['PropertySourcesOut']
export type ValueSource = components['schemas']['ValueSourceOut']

export const LENGTH_UNIT = 'mm'
export const DENSITY_UNIT = 'kg/m3'

export interface MaterialQuery {
  q?: string
  /** 분류로 좁힌다. 서버가 정확히 일치로 거른다. */
  family?: string
  category?: string
  scope?: 'all' | 'mine' | 'global'
  limit?: number
  offset?: number
}

function search(query: MaterialQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export const materialsApi = {
  list: (query: MaterialQuery = {}) => api.get<MaterialPage>(`/materials${search(query)}`),

  /**
   * 실제로 쓰이고 있는 분류 조합. **고정 목록을 화면에 박지 않는다** — 부서가
   * 새 분류를 쓰기 시작하면 고를 수 없게 되고, 그때 사람은 "재료가 없다" 로 읽는다.
   */
  classifications: () => api.get<Classification[]>('/materials/classifications'),
  get: (id: string) => api.get<Material>(`/materials/${id}`),
  create: (payload: MaterialCreate) => api.post<Material>('/materials', payload),
  update: (id: string, payload: MaterialUpdate) =>
    api.patch<Material>(`/materials/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/materials/${id}`),

  /** 어떤 값이 어디에 적혀 있고 무엇에 쓰이는지. 화면이 이 배치를 외우지 않는다. */
  propertySources: (id: string) =>
    api.get<PropertySources>(`/materials/${id}/property-sources`),

  /** 이름을 만드는 곳은 서버 하나다 — 화면은 규칙을 다시 구현하지 않고 물어본다. */
  previewName: (payload: NamePreviewRequest) =>
    api.post<NamePreview>('/materials/preview-name', payload),

  samples: (materialId: string) => api.get<Sample[]>(`/materials/${materialId}/samples`),
  createSample: (materialId: string, payload: SampleCreate) =>
    api.post<Sample>(`/materials/${materialId}/samples`, payload),
  removeSample: (id: string) => api.delete<void>(`/samples/${id}`),

  specimens: (sampleId: string) => api.get<Specimen[]>(`/samples/${sampleId}/specimens`),
  createSpecimen: (sampleId: string, payload: SpecimenCreate) =>
    api.post<Specimen>(`/samples/${sampleId}/specimens`, payload),
  /** 시편 속성 수정 — 치수·메모. 방향과 번호는 이름을 만드는 값이라 안 바꾼다. */
  updateSpecimen: (id: string, payload: SpecimenUpdate) =>
    api.patch<Specimen>(`/specimens/${id}`, payload),

  removeSpecimen: (id: string) => api.delete<void>(`/specimens/${id}`),
}
