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
/**
 * 조건 하나를 사람 말로. **아는 것은 짧게, 모르는 것은 그대로.**
 */
function fmtOne(key: string, value: unknown): string {
  const known = CONDITION_SYMBOLS[key]
  if (known) return known(value)
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  return `${key}=${text.length > 24 ? `${text.slice(0, 24)}…` : text}`
}

/**
 * **후보를 가르는 조건만.** 서버가 무리 안에서 값이 갈리는 키를 뽑아 준다
 * (`distinguishing`) — 겹치는 조건은 빼고 온다.
 *
 * 실측(2026-09-09): 값이 둘 이상인 조합의 **98%가 조건이 서로 다르다.** 같은 것을
 * 여러 번 잰 것이 아니라 다른 조건의 값이라는 뜻이고, 그래서 「무엇이 다른가」 가
 * 고를 때 가장 중요한 정보다. 전에는 사람이 긴 조건 문자열 넷을 눈으로 대조했다.
 */
export function fmtDistinguishing(
  distinguishing: Record<string, unknown> | null | undefined
): string[] {
  if (!distinguishing) return []
  return Object.entries(distinguishing)
    .filter(([key]) => !isBookkeeping(key))
    .map(([key, value]) => fmtOne(key, value))
}

/** 갈리는 것 말고 나머지 조건 — 회색으로 뒤에 둔다. */
export function fmtRestConditions(
  conditions: Record<string, unknown> | null | undefined,
  distinguishing: Record<string, unknown> | null | undefined
): string {
  if (!conditions) return ''
  const shown = new Set(Object.keys(distinguishing ?? {}))
  const rest = Object.fromEntries(
    Object.entries(conditions).filter(([key]) => !shown.has(key))
  )
  return fmtConditions(rest)
}

export function fmtConditions(conditions: Record<string, unknown> | null | undefined): string {
  if (!conditions) return ''
  const entries = Object.entries(conditions).filter(([key]) => !isBookkeeping(key))
  const parts = entries.map(([key, value]) => fmtOne(key, value))
  if (parts.length <= 4) return parts.join(' · ')
  return `${parts.slice(0, 4).join(' · ')} 외 ${parts.length - 4}`
}

/**
 * 채택 가능한 물성 — **서버의 매핑이 정본이다**(`/catalog/properties/adoptable`).
 *
 * 전에는 이 표가 여기와 MCP 와 백엔드에 세 벌로 박혀 있었고, 기준정보의 물성
 * 매핑에서 항목을 이어도 채우기에는 아무 일도 안 일어났다(2026-09-12). 이제 매핑
 * 화면에서 이은 것이 곧 담을 수 있는 것이다. 눈금이 붙은 매핑(경도 HV)은 담을 때
 * 그 눈금으로 들어간다.
 *
 * **단위 변환은 없다.** 카탈로그 값은 SI 로 저장돼 있고, 선언 물성은 `input_unit`
 * 을 비우면 정본 SI 로 받는다 — 숫자가 그대로 흐른다. 차원이 다른 것은 이을 때
 * 서버가 막는다(MNX-CATALOG-0029).
 */
export type AdoptableSlot = components['schemas']['PropertyAdoptableOut']

/** 키 → 자리. 같은 키에 눈금별로 여럿이면 첫 것을 쓴다 — 문헌값은 눈금이 하나다. */
export function slotsByKey(list: AdoptableSlot[]): Record<string, AdoptableSlot> {
  const out: Record<string, AdoptableSlot> = {}
  for (const one of list) if (!(one.property_key in out)) out[one.property_key] = one
  return out
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

/**
 * 채택 시 값에 붙일 참고문헌 문자열 — 제목·연도·DOI 까지, 등급 표기와 함께.
 *
 * **고른 이유가 함께 간다**(2026-09-09). 문헌에 후보가 넷 있었고 그중 하나를 골랐다면,
 * 담긴 값만 봐서는 왜 그것인지 알 수 없었다 — 반년 뒤에 그 재료로 해석을 돌리는
 * 사람은 「이 CTE 가 Tg 아래 값인가」 를 물성 탭에서 답할 수 있어야 한다. 그래서
 * **후보를 가르던 조건**(`distinguishing`)을 문장 끝에 적는다.
 *
 * 후보가 하나뿐이면 아무것도 안 붙는다 — 가를 것이 없기 때문이다.
 */
export function adoptionReference(value: CatalogValue): string {
  const source = value.source
  const parts = [
    source?.title ?? source?.publisher ?? '카탈로그',
    source?.year ? String(source.year) : null,
    source?.doi ? `doi:${source.doi}` : null,
    value.source_detail,
  ].filter(Boolean)
  const varying = fmtDistinguishing(value.distinguishing as Record<string, unknown> | null)
  const chosen = varying.length > 0 ? ` — ${varying.join(' · ')}` : ''
  return `${parts.join(' · ')} (문헌 물성 카탈로그, ${TIER_LABELS[value.quality_tier] ?? `t${value.quality_tier}`})${chosen}`
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

  /** 물성 매핑 — 문헌 키 · 사내 항목 · 잰 값이 한 줄에. 매핑 화면이 이것만으로 그린다. */
  propertyMapping: () => api.get<PropertyMapping>('/catalog/properties/mapping'),
  /** 사내 항목을 문헌 키에 잇는다. 눈금 있는 항목(경도)은 `scale` 이 필수다 — 서버가 막는다. */
  linkProperty: (payload: PropertyLinkCreate) =>
    api.post<PropertyLink>('/catalog/properties/links', payload),
  unlinkProperty: (linkId: string) => api.delete<void>(`/catalog/properties/links/${linkId}`),

  /**
   * 카탈로그에 직접 넣기 — MaterialTwin 에 없는 물성·재료·값(2026-09-12).
   * 정의의 키는 서버가 `local.<domain>.<slug>` 로 만든다. 지우기는 직접 넣은 줄만.
   */
  createProperty: (payload: CatalogPropertyCreate) =>
    api.post<CatalogDefinition>('/catalog/properties', payload),
  deleteProperty: (key: string) =>
    api.delete<void>(`/catalog/properties/${encodeURIComponent(key)}`),
  createCatalogMaterial: (payload: CatalogMaterialCreate) =>
    api.post<CatalogMaterial>('/catalog/materials', payload),
  createValue: (materialId: string, payload: CatalogValueCreate) =>
    api.post<CatalogValueCreated>(`/catalog/materials/${materialId}/values`, payload),
  deleteValue: (valueId: string) => api.delete<void>(`/catalog/values/${valueId}`),
}

export type CatalogPropertyCreate = components['schemas']['CatalogPropertyCreate']
export type CatalogDefinition = components['schemas']['CatalogDefinitionOut']
export type CatalogMaterialCreate = components['schemas']['CatalogMaterialCreate']
export type CatalogValueCreate = components['schemas']['CatalogValueCreate']
export type CatalogValueCreated = components['schemas']['CatalogValueCreatedOut']

/** 카탈로그 도메인 — 서버 `contribute.DOMAINS` 와 같다. 새 값을 만들지 않는다. */
export const DOMAINS = Object.keys(DOMAIN_LABELS)

export type PropertyMapping = components['schemas']['PropertyMappingOut']
export type PropertyMappingRow = components['schemas']['PropertyMappingRowOut']
export type PropertyLink = components['schemas']['PropertyLinkOut']
export type PropertyLinkCreate = components['schemas']['PropertyLinkCreate']
export type PropertyUnlinkedItem = components['schemas']['PropertyUnlinkedItemOut']

/**
 * 종합값으로 담을 때의 참고문헌 — **무엇을 종합했는지 숫자로 남긴다.**
 *
 * 값 하나를 고른 것이 아니라 여럿을 묶은 것이므로, 그 사실과 범위가 남지 않으면
 * 나중에 되짚을 수 없다. 이 저장소는 **카드가 자기 근거를 들고 있어야 한다**는
 * 원칙 위에 서 있다(ADR 0009·0012).
 */
export function pooledReference(value: CatalogValue): string {
  const summary = value.summary as Record<string, number> | null
  if (!summary) return adoptionReference(value)
  const base = adoptionReference(value)
  const range =
    summary.min === summary.max
      ? `${summary.min}`
      : `${summary.min} ~ ${summary.max}`
  return `${base} — 같은 조건 ${summary.n}건 종합(중앙값, 범위 ${range})`
}
