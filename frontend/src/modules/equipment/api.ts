/**
 * 보유 장비 — **우리가 실제로 가진 설비 한 대 한 대.**
 *
 * 측정법(`metrology`)이 읽기 전용인 것과 반대다. 저기는 이관물이라 사람이 못
 * 고치고, 여기는 사내 자산이라 사람이 관리하는 것이 전부다.
 *
 * 화면이 지킬 것 둘:
 *   ① **얼굴은 장비명이다.** 사람은 「생기연 DMA」·「대형 챔버」 로 부르지
 *      자산번호로 부르지 않는다. 자산번호는 스티커와 대조할 때 쓴다.
 *   ② **조직은 부서다.** 기준정보에 조직 축을 두려다 걷어냈다 — 부서가 이미
 *      본부→팀 트리라, 상위 조직은 그 트리를 타고 나온다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type EquipmentUnit = components['schemas']['EquipmentUnitOut']
export type EquipmentPart = components['schemas']['EquipmentPartOut']
export type EquipmentCalibration = components['schemas']['EquipmentCalibrationOut']
export type EquipmentSummary = components['schemas']['EquipmentSummaryOut']
export type EquipmentSummaryRow = components['schemas']['EquipmentSummaryRow']
export type EquipmentBulkResult = components['schemas']['EquipmentBulkResult']

export const STATUS_LABELS: Record<string, string> = {
  active: '가동',
  maintenance: '점검·수리',
  idle: '유휴',
  retired: '폐기',
}

export const OWNERSHIP_LABELS: Record<string, string> = {
  internal: '사내',
  external: '위탁',
}

export const PART_KIND_LABELS: Record<string, string> = {
  load_cell: '로드셀',
  extensometer: '신율계',
  chamber: '챔버',
  sensor: '센서',
  fixture: '지그',
  other: '기타',
}

export const CALIBRATION_RESULT_LABELS: Record<string, string> = {
  pass: '합격',
  conditional: '조건부',
  fail: '불합격',
}

/** 교정 만료가 임박했다고 볼 날 수. 서버의 `DUE_SOON_DAYS` 와 같아야 한다. */
export const DUE_SOON_DAYS = 30

/**
 * 교정 상태 한 마디.
 *
 * **「모른다」 를 「만료」 로 적지 않는다.** 유효기간이 안 적힌 성적서가 있고,
 * 그것을 만료로 칠하면 멀쩡한 장비가 빨갛게 물든다.
 */
export function calibrationState(
  validUntil: string | null | undefined
): { tone: 'none' | 'ok' | 'due' | 'over'; text: string } {
  if (!validUntil) return { tone: 'none', text: '기간 없음' }
  const left = Math.ceil(
    (new Date(validUntil).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  )
  if (left < 0) return { tone: 'over', text: `${-left}일 지남` }
  if (left <= DUE_SOON_DAYS) return { tone: 'due', text: `${left}일 남음` }
  return { tone: 'ok', text: validUntil }
}

export interface UnitQuery {
  q?: string
  status?: string
  ownership?: string
  workspace_id?: string
  lab_term_id?: string
  type_term_id?: string
  calibration_due?: boolean
  limit?: number
  offset?: number
}

function search(query: UnitQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export const equipmentApi = {
  units: (query: UnitQuery = {}) =>
    api.get<Page<EquipmentUnit>>(`/equipment/units${search(query)}`),
  unit: (id: string) => api.get<EquipmentUnit>(`/equipment/units/${id}`),
  summary: () => api.get<EquipmentSummary>('/equipment/summary'),

  create: (body: Record<string, unknown>) =>
    api.post<EquipmentUnit>('/equipment/units', body),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch<EquipmentUnit>(`/equipment/units/${id}`, body),
  remove: (id: string) => api.delete<void>(`/equipment/units/${id}`),

  parts: (id: string) => api.get<EquipmentPart[]>(`/equipment/units/${id}/parts`),
  addPart: (id: string, body: Record<string, unknown>) =>
    api.post<EquipmentPart>(`/equipment/units/${id}/parts`, body),
  removePart: (partId: string) => api.delete<void>(`/equipment/parts/${partId}`),

  calibrations: (id: string) =>
    api.get<EquipmentCalibration[]>(`/equipment/units/${id}/calibrations`),
  addCalibration: (id: string, body: Record<string, unknown>) =>
    api.post<EquipmentCalibration>(`/equipment/units/${id}/calibrations`, body),

  /** 붙여넣기 일괄 등록. **드라이런이 기본이다** — 서버가 그렇게 받는다. */
  bulk: (rows: Record<string, unknown>[], dryRun = true) =>
    api.post<EquipmentBulkResult>('/equipment/units/bulk', { rows, dry_run: dryRun }),
}
