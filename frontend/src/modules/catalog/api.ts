/**
 * 물성 카탈로그 — 문헌·데이터시트에서 채굴된 물성값의 보관소 (ADR 0027).
 *
 * **읽기 전용이다.** 데이터는 서버의 이관 스크립트로만 들어오고, 화면은 보고
 * 고르기만 한다. 값마다 출처와 품질 등급(tier 1~4)이 붙어 있다 — **4는 근거
 * 없는 값**(계산·추정·가정)이라 화면이 반드시 구별해 보여 준다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { display } from '@/shared/units'

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
 * 단위를 시스템 철자로 — MT `kg/m^3`·`J/(kg*K)` 를 matcore 정본 스타일
 * `kg/m3`·`J/(kg.K)` 로 적는다(2026-09-06 사용자 요청). **표기만이다** — 저장은
 * 원본 그대로(무손실)고, 이 변환은 지수 캐럿 제거·곱 기호 통일이라 물리량이
 * 바뀌지 않는다. 시스템에 없는 눈금(HV·ShoreA)도 스타일만 따라간다.
 */
export function systemUnit(unit: string): string {
  return unit.replaceAll('^', '').replaceAll('*', '.')
}

/** 숫자만 — 공학 표기. 아주 크거나 작으면 지수, 아니면 유효숫자 5자리. */
function fmtNumber(value: number): string {
  const magnitude = Math.abs(value)
  return magnitude !== 0 && (magnitude >= 1e5 || magnitude < 1e-3)
    ? value.toExponential(3)
    : String(Number(value.toPrecision(5)))
}

/** 값 표기(SI) — 단위는 시스템 철자로, 무차원(`1`)은 숨긴다. */
export function fmtValue(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const pretty = unit && unit !== '1' ? ` ${systemUnit(unit)}` : ''
  return `${fmtNumber(value)}${pretty}`
}

/** 단위 모드 — 시스템 나머지 화면과 같은 표시용(실무 단위)이 기본이다. */
export type UnitMode = 'display' | 'si'

/**
 * 값 표기(모드 선택) — 표시용이면 공용 표(`shared/units.ts`)로 환산해 그린다.
 * 저장·API 는 언제나 SI 고, 환산은 화면에서만 한다(ADR 0004). 표에 없는
 * 단위(HV·전기 차원 등)는 SI 철자 그대로 남는다.
 */
export function fmtValueAs(
  mode: UnitMode,
  value: number | null | undefined,
  unit?: string | null
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (mode === 'si' || !unit || unit === '1') return fmtValue(value, unit)
  const si = systemUnit(unit)
  const shown = display(si)
  if (shown.factor === 1 && shown.offset === 0) return fmtValue(value, unit)
  const converted = value * shown.factor + shown.offset
  return `${fmtNumber(converted)}${shown.unit ? ` ${shown.unit}` : ''}`
}

/** 단위 라벨(모드 선택) — 표시용이면 공용 표의 단위, 아니면 시스템 철자. */
export function unitLabelAs(mode: UnitMode, unit?: string | null): string {
  if (!unit || unit === '1') return ''
  const si = systemUnit(unit)
  if (mode === 'si') return si
  return display(si).unit || si
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
      // **변수와 그 단위는 이제 「물성」 열이 말한다**(ADR 0029). 조건에 또 적으면
      // 같은 말이 두 곳에 서고, 정작 조건다운 것(온도·속도)이 뒤로 밀린다.
      'term',
      'unit_of_term',
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

/**
 * 채택 가능한 물성 — backend catalog/mapping.py 의 PROPERTY_ITEM_MAP 과 짝.
 *
 * **단위 변환은 없다.** 카탈로그 값은 SI 로 저장돼 있고, 선언 물성은
 * `input_unit` 을 비우면 정본 SI 로 받는다 — 숫자가 그대로 흐른다. 표기 등가
 * (`J/(kg*K)` ↔ `J/(kg.K)`)는 백엔드 계약 테스트가 지킨다. 이 표에 없는
 * 물성(비SI 눈금·matcore 밖 차원)은 채택 목록에 오르지 않는다.
 */
export const ADOPTABLE: Record<
  string,
  { item: string; place: 'declared' } | { item: string; place: 'column'; field: 'density' | 'poisson_ratio' }
> = {
  'mechanical.youngs_modulus': { item: '탄성계수', place: 'declared' },
  'mechanical.shear_modulus': { item: '전단탄성계수', place: 'declared' },
  'mechanical.yield_strength': { item: '항복강도', place: 'declared' },
  'mechanical.tensile_strength': { item: '인장강도', place: 'declared' },
  'mechanical.elongation_at_break': { item: '연신율', place: 'declared' },
  'thermal.specific_heat': { item: '비열', place: 'declared' },
  'thermal.conductivity': { item: '열전도율', place: 'declared' },
  'thermal.expansion_linear': { item: '선팽창계수(CTE)', place: 'declared' },
  'physical.density': { item: '밀도', place: 'column', field: 'density' },
  'mechanical.poisson_ratio': { item: '포아송비', place: 'column', field: 'poisson_ratio' },
}

/** 카탈로그 출처 종류 → 선언 물성의 source 어휘. */
export function adoptionSource(value: CatalogValue): string {
  if (value.quality_tier === 4 || value.method === 'estimated' || value.method === 'computed') {
    return 'estimate'
  }
  const kind = value.source?.kind
  if (kind === 'datasheet') return 'datasheet'
  if (kind === 'standard') return 'standard'
  return 'literature'
}

/** 채택 시 값에 붙일 참고문헌 문자열 — 제목·연도·DOI 까지, 등급 표기와 함께. */
export function adoptionReference(value: CatalogValue): string {
  const source = value.source
  const parts = [
    source?.title ?? source?.publisher ?? '카탈로그',
    source?.year ? String(source.year) : null,
    source?.doi ? `doi:${source.doi}` : null,
    value.source_detail,
  ].filter(Boolean)
  return `${parts.join(' · ')} (문헌 물성 카탈로그, ${TIER_LABELS[value.quality_tier] ?? `t${value.quality_tier}`})`
}

export type CatalogLink = components['schemas']['CatalogLinkOut']
export type DeckMatchRow = components['schemas']['DeckMatchRowOut']
export type DeckBuilt = components['schemas']['DeckBuiltOut']

/** 카탈로그에서 낼 수 있는 덱 형식 — 스칼라 렌더러만 (서버 FORMATS 와 짝). */
export const DECK_FORMATS = [
  { key: 'dyna_elastic', label: 'LS-DYNA 탄성 (*MAT_ELASTIC)' },
  { key: 'dyna_thermal', label: 'LS-DYNA 열물성 (*MAT_THERMAL_ISOTROPIC)' },
] as const

/** 덱 단위계 — 내장 두 계 (서버 systems.get 과 짝). */
export const DECK_UNITS = [
  { key: 'si', label: 'SI (kg · m · s · Pa)' },
  { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)' },
] as const

export type CompareResult = components['schemas']['CatalogCompareOut']
export type AshbyAxis = components['schemas']['AshbyAxisOut']
export type AshbyResult = components['schemas']['AshbyOut']
export type CoverageResult = components['schemas']['CatalogCoverageOut']

export const catalogApi = {
  compare: (ids: string[]) =>
    api.get<CompareResult>(`/catalog/compare?ids=${ids.join(',')}`),
  axes: () => api.get<AshbyAxis[]>('/catalog/axes'),
  ashby: (x: string, y: string, color: 'category' | 'subsystem') =>
    api.get<AshbyResult>(
      `/catalog/ashby?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}&color=${color}`
    ),
  coverage: () => api.get<CoverageResult>('/catalog/coverage'),
  deckMatch: (text: string) => api.post<DeckMatchRow[]>('/catalog/deck/match', { text }),
  deckBuild: (body: {
    items: { mid: number; catalog_material_id: string }[]
    format: string
    units?: string
  }) => api.post<DeckBuilt>('/catalog/deck/build', body),
  summary: () => api.get<CatalogSummary>('/catalog/summary'),
  /** 사내 재료의 문헌 연결. 없어도 200 — catalog_material_id 가 null 이다. */
  link: (materialId: string) => api.get<CatalogLink>(`/catalog/links/${materialId}`),
  setLink: (materialId: string, catalogMaterialId: string) =>
    api.put<CatalogLink>(`/catalog/links/${materialId}`, {
      catalog_material_id: catalogMaterialId,
    }),
  clearLink: (materialId: string) => api.delete<void>(`/catalog/links/${materialId}`),
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
