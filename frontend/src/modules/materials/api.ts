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
type SampleUpdate = components['schemas']['SampleUpdateRequest']
type SpecimenCreate = components['schemas']['SpecimenCreateRequest']
type NamePreviewRequest = components['schemas']['NamePreviewRequest']

/**
 * 화면이 쓰는 단위. 값과 함께 **항상 명시해서 보낸다** — 서버가 SI 로 바꿔 저장하고
 * 무엇으로 입력받았는지 기록한다. 생략 가능하게 두면 "이 값이 mm 였나 m 였나"를
 * 나중에 아무도 답할 수 없다.
 */
export type PropertySources = components['schemas']['PropertySourcesOut']
/**
 * 시편 치수 한 벌 — **칸 목록은 규격이 정한다.**
 *
 * 화면에 두께·폭·게이지 세 칸을 박아 두었더니 환봉을 담을 자리가 없었다.
 * 이제 규격이 자기 칸을 갖고(ADR 0010) 화면은 그것을 그린다.
 */
export type SpecimenSizes = components['schemas']['SpecimenSizesOut']
export type SpecimenSize = components['schemas']['SpecimenSizeOut']
export type ValueSource = components['schemas']['ValueSourceOut']
/**
 * 시험이 주지 않아 사람이 적은 물성 한 줄(ADR 0016).
 *
 * 값은 언제나 SI(`value_si`)로 오고 적은 단위(`input_unit`)가 함께 온다 —
 * `2.06e11` 만 돌려주면 자기가 적은 값인지 알기 어렵다.
 */
export type DeclaredProperty = components['schemas']['DeclaredPropertyOut']
/** 넣을 수 있는 물성 항목. **목록은 기준정보가 정한다**(D7). */
export type PropertyItem = components['schemas']['PropertyItemOut']

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

  /**
   * 넣을 수 있는 물성 항목. 기준정보의 `물성 항목` 축이 정한다.
   *
   * **재료마다 다르지 않다** — 재료 id 를 안 받는 이유다. 무엇을 넣을 수
   * 있는지는 부서의 결정이고 재료의 성질이 아니다.
   */
  propertyItems: () => api.get<PropertyItem[]>('/materials/property-items'),

  /** 어떤 값이 어디에 적혀 있고 무엇에 쓰이는지. 화면이 이 배치를 외우지 않는다. */
  propertySources: (id: string) =>
    api.get<PropertySources>(`/materials/${id}/property-sources`),

  /** 이름을 만드는 곳은 서버 하나다 — 화면은 규칙을 다시 구현하지 않고 물어본다. */
  previewName: (payload: NamePreviewRequest) =>
    api.post<NamePreview>('/materials/preview-name', payload),

  samples: (materialId: string) => api.get<Sample[]>(`/materials/${materialId}/samples`),
  createSample: (materialId: string, payload: SampleCreate) =>
    api.post<Sample>(`/materials/${materialId}/samples`, payload),
  /**
   * 시료 속성 수정 — 로트·벤더·밀도·메모. 번호는 이름을 만드는 값이라 안 바꾼다.
   *
   * 없어서 막다른 길이 됐다: 로트를 잘못 적으면 고칠 수 없고, 지우려 해도
   * 시편이 달려 있으면 서버가 막는다.
   */
  updateSample: (id: string, payload: SampleUpdate) =>
    api.patch<Sample>(`/samples/${id}`, payload),
  removeSample: (id: string) => api.delete<void>(`/samples/${id}`),

  specimens: (sampleId: string) => api.get<Specimen[]>(`/samples/${sampleId}/specimens`),
  createSpecimen: (sampleId: string, payload: SpecimenCreate) =>
    api.post<Specimen>(`/samples/${sampleId}/specimens`, payload),
  /** 시편 속성 수정 — 치수·메모. 방향과 번호는 이름을 만드는 값이라 안 바꾼다. */
  updateSpecimen: (id: string, payload: SpecimenUpdate) =>
    api.patch<Specimen>(`/specimens/${id}`, payload),

  /**
   * 이 시편이 가질 수 있는 치수 칸과 지금 값. 규격이 정한다.
   *
   * **공칭과 실측을 나란히 준다** — 합쳐서 하나로 주면 사람은 전부 실측으로 읽고,
   * "이 두께가 규격값인가 잰 값인가" 를 나중에 답할 수 없다.
   */
  dimensions: (id: string) => api.get<SpecimenSizes>(`/specimens/${id}/dimensions`),

  /** 잰 값만 보낸다(SI). **키를 빼면 그 칸을 안 잰 것이 된다.** */
  saveDimensions: (id: string, dimensions: Record<string, number>) =>
    api.put<SpecimenSizes>(`/specimens/${id}/dimensions`, { dimensions }),

  removeSpecimen: (id: string) => api.delete<void>(`/specimens/${id}`),
}
