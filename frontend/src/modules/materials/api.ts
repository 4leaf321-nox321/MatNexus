/** 재료·시료·시편 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { display } from '@/shared/units'

export type Material = components['schemas']['MaterialOut']
export type MaterialPage = components['schemas']['Page_MaterialOut_']
export type Sample = components['schemas']['SampleOut']
export type Specimen = components['schemas']['SpecimenOut']
export type NamePreview = components['schemas']['NamePreviewOut']
export type Classification = components['schemas']['ClassificationOut']
/** 못 지운 것과 그 이유. */
export type MaterialDeleteResult = components['schemas']['MaterialDeleteOut']
export type BulkRequest = components['schemas']['BulkRequest']
/** 무엇이 만들어졌고 어느 줄이 막혔는가. */
export type BulkResult = components['schemas']['BulkOut']

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
/** 넣을 때. `value` 는 `input_unit` 단위의 값이고 서버가 SI 로 바꾼다. */
export type DeclaredPropertyIn = components['schemas']['DeclaredPropertyIn']
/** 밀시트가 말한 값과 우리가 잰 값을 나란히(ADR 0016). */
export type MillCheck = components['schemas']['MillCheckOut']
/** 넣을 수 있는 물성 항목. **목록은 기준정보가 정한다**(D7). */
export type PropertyItem = components['schemas']['PropertyItemOut']

/**
 * 시편 방향. **서버의 `ORIENTATIONS` 와 같은 목록이다.**
 *
 * 세 화면이 각자 배열을 적어 두고 있었다 — 하나를 늘리면 나머지 둘이 조용히
 * 뒤처진다. 재료 모듈이 시편의 주인이라 여기에 둔다.
 */
export const ORIENTATIONS = ['MD', 'TD', 'DD', 'NA'] as const

/**
 * 길이를 **화면에서 받아 서버로 보내는** 단위.
 *
 * 표(`shared/units`)에서 읽는다 — 사람은 표시 단위로 치고, 우리는 그것을
 * 그대로 보내면서 단위 이름을 함께 적는다(서버가 SI 로 바꾼다).
 *
 * `'mm'` 이라고 박아 두었더니 **라벨을 손으로 적는 자리가 생겼다** — 실측
 * 두께 (mm)·스펙 두께 (mm)·시편 치수 일괄 지정 (mm) 넷이 그랬다. 표를 바꾸면
 * 그 라벨들은 옛 단위를 적은 채 새 값을 받는다. 밀도 쪽 주석이 같은 함정을
 * 이미 적어 두고 있었다.
 */
export const LENGTH_UNIT = display('m').unit
/**
 * 밀도를 **화면에서 받아 서버로 보내는** 단위(v1.88.0 에 `kg/m3` 에서 옮김).
 *
 * 위첨자 없는 표기다 — 서버의 `matcore/units` 표가 아는 기호가 `tonne/mm3` 다.
 * 사람에게 보일 기호는 `shared/units` 의 표가 정한다(`tonne/mm³`). 라벨에
 * 손으로 적지 않는다: 두 곳에 적으면 하나만 바뀌고, 그때 화면은 kg/m³ 라고
 * 적힌 칸에 tonne/mm³ 값을 받는다.
 */
export const DENSITY_UNIT = 'tonne/mm3'

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
   * 고른 것을 한 번에 지운다. **하나가 막혀도 나머지는 지운다** — 막힌 것은
   * 이유와 함께 돌아온다(권한 · 시료가 남음).
   */
  removeMany: (materialIds: string[]) =>
    api.post<MaterialDeleteResult>('/materials/delete', { material_ids: materialIds }),

  /**
   * 재료·시료·시편을 한 번에. 본문은 **나무**다 — 화면의 평평한 표를
   * `bulkRows.group` 이 묶어서 보낸다.
   */
  bulk: (body: BulkRequest) => api.post<BulkResult>('/materials/bulk', body),

  /**
   * 넣을 수 있는 물성 항목. 기준정보의 `물성 항목` 축이 정한다.
   *
   * **재료마다 다르지 않다** — 재료 id 를 안 받는 이유다. 무엇을 넣을 수
   * 있는지는 부서의 결정이고 재료의 성질이 아니다.
   */
  propertyItems: (level?: string) =>
    api.get<PropertyItem[]>(
      `/materials/property-items${level ? `?level=${encodeURIComponent(level)}` : ''}`
    ),

  /**
   * 밀시트가 말한 값과 **우리가 잰 값을 나란히**(ADR 0016).
   *
   * 밀시트는 「이 로트가 규격에 맞나」를 증명하는 문서다(EN 10204 3.1). 그
   * 증명이 맞는지 확인할 자리가 지금까지 없었다 — 값은 문서에, 시험 결과는
   * 시스템에 따로 있었다.
   */
  millCheck: (sampleId: string) =>
    api.get<MillCheck>(`/samples/${sampleId}/mill-check`),

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
