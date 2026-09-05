/**
 * 측정법 — **「그 물성은 무엇으로 재는가」** (MaterialTwin 이식 4단계).
 *
 * 읽기 전용이다. 데이터는 서버의 이관 스크립트로만 들어온다. 화면이 지킬 것
 * 둘: ① 장비 카탈로그에 있는 것과 **우리가 보유한 것**을 가른다 ② 물성↔장비
 * 매핑은 사람의 판단이라 확신도(high·medium·low)가 high 가 아니면 표시를 단다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type MetrologySummary = components['schemas']['MetrologySummaryOut']
export type MetrologyCoverage = components['schemas']['MetrologyCoverageOut']
export type MetrologyCoverageRow = components['schemas']['MetrologyCoverageRowOut']
export type MetrologyProperty = components['schemas']['MetrologyPropertyOut']
export type MetrologyCapability = components['schemas']['MetrologyCapabilityOut']

/** 장비 분류의 화면 라벨. */
export const INSTRUMENT_CATEGORY_LABELS: Record<string, string> = {
  thermal: '열',
  mechanical: '기계',
  surface: '표면',
  chemical: '화학',
  particle: '입자',
  optical: '광학',
  electrical: '전기',
  ndt: '비파괴',
  reliability: '신뢰성',
}

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: '확실',
  medium: '중간',
  low: '낮음',
}

/** 측정 범위 표기 — `up to` 문구는 하한이 빈 칸이라 `≤ 상한` 으로 적는다. */
export function fmtRange(
  min: number | null | undefined,
  max: number | null | undefined,
  unit: string | null | undefined
): string {
  const suffix = unit ? ` ${unit}` : ''
  if (min != null && max != null) return `${min} ~ ${max}${suffix}`
  if (max != null) return `≤ ${max}${suffix}`
  if (min != null) return `≥ ${min}${suffix}`
  return '—'
}

/** 시편 온도 범위(K) — 장비 내부 온도계 범위가 아니다(원본 함정 대장). */
export function fmtTemperature(
  minK: number | null | undefined,
  maxK: number | null | undefined
): string {
  if (minK == null && maxK == null) return '—'
  const left = minK != null ? `${minK}` : ''
  const right = maxK != null ? `${maxK}` : ''
  return `${left} ~ ${right} K`
}

export const metrologyApi = {
  summary: () => api.get<MetrologySummary>('/metrology/summary'),
  coverage: () => api.get<MetrologyCoverage>('/metrology/coverage'),
  byProperty: (key: string) =>
    api.get<MetrologyProperty>(`/metrology/by-property/${encodeURIComponent(key)}`),
}
