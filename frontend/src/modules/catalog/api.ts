/**
 * 물성 카탈로그 — 문헌·데이터시트에서 채굴된 물성값의 보관소 (ADR 0027).
 *
 * **읽기 전용이다.** 데이터는 서버의 이관 스크립트로만 들어오고, 화면은 보고
 * 고르기만 한다. 값마다 출처와 품질 등급(tier 1~4)이 붙어 있다 — **4는 근거
 * 없는 값**(계산·추정·가정)이라 화면이 반드시 구별해 보여 준다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type CatalogSummary = components['schemas']['CatalogSummaryOut']
export type CatalogMaterial = components['schemas']['CatalogMaterialOut']
export type CatalogMaterialPage = components['schemas']['CatalogMaterialPage']
export type CatalogMaterialDetail = components['schemas']['CatalogMaterialDetailOut']
export type CatalogValue = components['schemas']['CatalogValueOut']

/** 품질 등급 라벨 — 서버 독트린 그대로. 4는 신뢰 경로에서 빠진다. */
export const TIER_LABELS: Record<number, string> = {
  1: '실측',
  2: '핸드북',
  3: '2차 인용',
  4: '추정',
}

/**
 * MT category → 우리 family 축 표기 (backend catalog/mapping.py 와 짝).
 * 저장은 원본 그대로(무손실) 두고 **표기만** 우리 체계로 잇는다.
 */
export const CATEGORY_LABELS: Record<string, string> = {
  metal: 'Metal',
  polymer: 'Polymer',
  ceramic: 'Ceramic',
  composite: 'Composite',
  rubber: 'Rubber',
  foam: 'Foam',
  molecular: 'Molecular',
}

/** 물성 도메인 12종의 화면 라벨. */
export const DOMAIN_LABELS: Record<string, string> = {
  mechanical: '기계',
  thermal: '열',
  physical: '물리',
  chemical: '화학',
  optical: '광학',
  electrical: '전기',
  interface: '계면',
  structure: '구조',
  rheological: '유변',
  magnetic: '자성',
  surface: '표면',
  acoustic: '음향',
}

/**
 * 값 표기 — 공학 표기. 아주 크거나 작은 값은 지수, 나머지는 유효숫자 5자리에서
 * 끝 0을 지운다. 단위의 `*` 는 `·` 로, 무차원(`1`)은 숨긴다.
 */
export function fmtValue(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const magnitude = Math.abs(value)
  const number =
    magnitude !== 0 && (magnitude >= 1e5 || magnitude < 1e-3)
      ? value.toExponential(3)
      : String(Number(value.toPrecision(5)))
  const pretty = unit && unit !== '1' ? ` ${unit.replaceAll('*', '·')}` : ''
  return `${number}${pretty}`
}

/** 조건이 아니라 관리 기록인 키 — 화면 조건 줄에서 뺀다 (서버와 같은 규칙). */
export function isBookkeeping(key: string): boolean {
  return (
    key.startsWith('verdict_') ||
    key.endsWith('_before_correction') ||
    [
      'corrected_by',
      'correction_reason',
      'correction_evidence',
      'moved_from_material',
      'moved_from_source',
      'merge_verdict',
      'direction_verbatim',
    ].includes(key)
  )
}

const CONDITION_SYMBOLS: Record<string, (v: unknown) => string> = {
  temperature_k: (v) => `T ${String(v)} K`,
  temperature_c: (v) => `T ${String(v)} ℃`,
  wavelength_nm: (v) => `λ ${String(v)} nm`,
  humidity_pct: (v) => `RH ${String(v)}%`,
  frequency_hz: (v) => `f ${String(v)} Hz`,
}

/** 조건을 짧게 — 아는 키는 기호로, 나머지는 key=value 로. 길면 「외 n」. */
export function fmtConditions(conditions: Record<string, unknown> | null | undefined): string {
  if (!conditions) return ''
  const entries = Object.entries(conditions).filter(([key]) => !isBookkeeping(key))
  const parts = entries.map(([key, value]) => {
    const known = CONDITION_SYMBOLS[key]
    if (known) return known(value)
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
    return `${key}=${text.length > 24 ? `${text.slice(0, 24)}…` : text}`
  })
  if (parts.length <= 4) return parts.join(' · ')
  return `${parts.slice(0, 4).join(' · ')} 외 ${parts.length - 4}`
}

export const catalogApi = {
  summary: () => api.get<CatalogSummary>('/catalog/summary'),
  materials: (params: {
    q?: string
    subsystem?: string
    category?: string
    limit?: number
    offset?: number
  }) => {
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) search.set(key, String(value))
    }
    const suffix = search.toString()
    return api.get<CatalogMaterialPage>(`/catalog/materials${suffix ? `?${suffix}` : ''}`)
  },
  material: (id: string) => api.get<CatalogMaterialDetail>(`/catalog/materials/${id}`),
}
