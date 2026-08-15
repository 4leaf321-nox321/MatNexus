/** 재료·시료·시편 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Material = components['schemas']['MaterialOut']
export type MaterialPage = components['schemas']['Page_MaterialOut_']
export type Sample = components['schemas']['SampleOut']
export type Specimen = components['schemas']['SpecimenOut']
export type NamePreview = components['schemas']['NamePreviewOut']

type MaterialCreate = components['schemas']['MaterialCreateRequest']
type MaterialUpdate = components['schemas']['MaterialUpdateRequest']
type SampleCreate = components['schemas']['SampleCreateRequest']
type SpecimenCreate = components['schemas']['SpecimenCreateRequest']
type NamePreviewRequest = components['schemas']['NamePreviewRequest']

/**
 * 화면이 쓰는 단위. 값과 함께 **항상 명시해서 보낸다** — 서버가 SI 로 바꿔 저장하고
 * 무엇으로 입력받았는지 기록한다. 생략 가능하게 두면 "이 값이 mm 였나 m 였나"를
 * 나중에 아무도 답할 수 없다.
 */
export const LENGTH_UNIT = 'mm'
export const DENSITY_UNIT = 'kg/m3'

export interface MaterialQuery {
  q?: string
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
  get: (id: string) => api.get<Material>(`/materials/${id}`),
  create: (payload: MaterialCreate) => api.post<Material>('/materials', payload),
  update: (id: string, payload: MaterialUpdate) =>
    api.patch<Material>(`/materials/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/materials/${id}`),

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
  removeSpecimen: (id: string) => api.delete<void>(`/specimens/${id}`),
}
