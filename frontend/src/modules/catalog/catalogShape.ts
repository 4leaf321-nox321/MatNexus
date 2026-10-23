/**
 * 문헌 재료 상세를 **체계적으로 펴는 계산**(2026-10-22, ADR 0067) — 그리지 않고 모양만 만든다.
 *
 *   propertyGroups   물성 하나에 한 줄 — 대표값 · 값 수 · 등급 · 갈리는 조건의 범위
 *   autoCurves       같은 물성의 값이 조건축 하나로만 갈리면 그 축을 따라 이은 선. **저장된
 *                    묶음이 아니라 화면이 이은 것이다** — 이관해 온 값에는 묶음 id 가 없다
 *                    (사용자 결정 2026-10-22: 저장된 값은 그대로 두고 화면에서만 잇는다)
 *   seriesCurves     직접 넣은 한 벌(곡선)의 열마다 선
 *   sourceRows       출처 하나에 한 줄 — 값 수 · 물성 수 · 등급
 *
 * 전에는 값 하나가 한 줄이라, 값이 366건인 재료(SAC-Q)는 같은 물성 이름이 수십 줄 섰고 그것이
 * 온도를 따라 이어진 한 곡선이라는 것은 조건 칸을 눈으로 대조해야 알았다.
 */

import { fmtConditions, isBookkeeping } from '@/modules/catalog/api'
import type { CatalogSeries, CatalogValue } from '@/modules/catalog/api'

type Source = NonNullable<CatalogValue['source']>

/** 선으로 이을 최소 점 수. 둘은 「값 둘」 이지 곡선이라 부르기 어렵다. */
export const MIN_CURVE_POINTS = 3

/** 축이 될 수 없는 조건 — 가정 표지 · 계수 묶음 표지. */
const NOT_AXIS = new Set(['assumption', 'model', 'set_id', 'n_terms'])

/**
 * 축 키 → [이름, SI 단위]. 단위는 표시 단위가 아니라 **저장 단위**다 — 표시는 `shared/units`
 * 표가 정한다(K → °C). 모르는 축은 키 그대로 · 단위 없이 그린다.
 */
export const AXIS_META: Record<string, [string, string | null]> = {
  temperature_k: ['온도', 'K'],
  temperature_c: ['온도', '°C'],
  strain_pct: ['변형률', '%'],
  strain: ['변형률', null],
  strain_rate_s: ['변형률 속도', '1/s'],
  strain_rate_1_s: ['변형률 속도', '1/s'],
  frequency_hz: ['주파수', 'Hz'],
  time_s: ['시간', 's'],
  duration_h: ['시간', 'h'],
  aging_hours: ['노화 시간', 'h'],
  aging_days: ['노화 일수', null],
  wavelength_nm: ['파장', 'nm'],
  wavelength_m: ['파장', 'm'],
  humidity_pct: ['습도', '%'],
  humidity_rh: ['습도', '%'],
  thickness_m: ['두께', 'm'],
  thickness_um: ['두께', 'µm'],
  depth_um: ['깊이', 'µm'],
  load_n: ['하중', 'N'],
  cycles: ['수명(반복수)', null],
}

/** 자릿수로 펼쳐 보는 축 — 속도 · 주파수 · 시간은 몇 자리에 걸쳐 잰다. */
export const LOG_AXES = new Set(['strain_rate_s', 'strain_rate_1_s', 'frequency_hz', 'time_s', 'cycles'])

export function axisName(key: string): string {
  return AXIS_META[key]?.[0] ?? key
}

export function axisUnit(key: string): string | null {
  return AXIS_META[key]?.[1] ?? null
}

function numberAt(value: CatalogValue, key: string): number | null {
  const raw = (value.conditions as Record<string, unknown> | null)?.[key]
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null
}

function canBeAxis(key: string): boolean {
  return !isBookkeeping(key) && !NOT_AXIS.has(key)
}

export interface AxisRange {
  key: string
  min: number
  max: number
}

export interface PropertyGroup {
  propertyKey: string
  name: string
  domain: string
  symbol: string | null
  values: CatalogValue[]
  /** 대표값 — 서버가 고른 대표, 없으면 첫 값. */
  head: CatalogValue
  /** 등급들(오름차순, 겹치지 않게). */
  tiers: number[]
  /** 값마다 갈리는 수 조건의 범위 — 「온도 25~150 °C」. */
  ranges: AxisRange[]
  /** 계수 묶음의 항만 있는 물성(Anand 상수 …) — 낱값이 아니라 「계수 묶음」 탭에서 본다. */
  parameterized: boolean
  /** 이 물성의 선 수(입력한 곡선 + 화면이 이은 것). */
  curves: number
}

/** 물성 하나에 한 줄. 서버가 준 차례(분야 → 물성, 대표 먼저)를 지킨다. */
export function propertyGroups(values: CatalogValue[], lines: CurveLine[] = []): PropertyGroup[] {
  const order: string[] = []
  const byKey = new Map<string, CatalogValue[]>()
  for (const value of values) {
    const list = byKey.get(value.property_key)
    if (list) list.push(value)
    else {
      byKey.set(value.property_key, [value])
      order.push(value.property_key)
    }
  }
  const curveCount = new Map<string, number>()
  for (const line of lines) curveCount.set(line.propertyKey, (curveCount.get(line.propertyKey) ?? 0) + 1)
  return order.map((key) => {
    const list = byKey.get(key) ?? []
    const scalars = list.filter((one) => !one.formula_term)
    const head =
      scalars.find((one) => one.representative && !one.source_missing_at) ?? scalars[0] ?? list[0]
    return {
      propertyKey: key,
      name: head.property_name,
      domain: head.domain,
      symbol: head.symbol ?? null,
      values: list,
      head,
      tiers: [...new Set(list.map((one) => one.quality_tier))].sort((a, b) => a - b),
      ranges: rangesOf(scalars),
      parameterized: scalars.length === 0,
      curves: curveCount.get(key) ?? 0,
    }
  })
}

function rangesOf(values: CatalogValue[]): AxisRange[] {
  const seen = new Map<string, number[]>()
  for (const value of values) {
    for (const key of Object.keys((value.conditions as Record<string, unknown> | null) ?? {})) {
      if (!canBeAxis(key)) continue
      const at = numberAt(value, key)
      if (at === null) continue
      const list = seen.get(key) ?? []
      list.push(at)
      seen.set(key, list)
    }
  }
  const out: AxisRange[] = []
  for (const [key, list] of seen) {
    const min = Math.min(...list)
    const max = Math.max(...list)
    if (min !== max) out.push({ key, min, max })
  }
  return out
}

export interface CurveLine {
  id: string
  propertyKey: string
  name: string
  /** 값의 단위(정의의 SI). */
  unit: string | null
  axis: string
  /** 선을 가르는 나머지 조건 — 「aging=120 days · 10 /s」. */
  label: string
  /** `[x(축 단위), y(SI)]`, x 차례. */
  points: [number, number][]
  /** 선의 등급 — 점들 가운데 가장 낮은 신뢰(가장 큰 수). */
  tier: number
  source: Source | null
  /** 직접 넣은 한 벌이면 그 id. 화면이 이은 선은 null. */
  seriesId: string | null
}

function distinctX(values: CatalogValue[], axis: string): number {
  return new Set(values.map((one) => numberAt(one, axis))).size
}

/** 선을 가르는 열쇠 — 출처 + 축을 뺀 나머지 조건(관리 기록 · 가정 표지 제외). */
function signature(value: CatalogValue, axis: string): string {
  const conditions = (value.conditions as Record<string, unknown> | null) ?? {}
  const rest = Object.entries(conditions)
    .filter(([key]) => key !== axis && !isBookkeeping(key) && key !== 'assumption')
    .sort(([left], [right]) => left.localeCompare(right))
  return JSON.stringify([value.source?.id ?? null, value.method ?? null, rest])
}

function lineOf(
  id: string,
  members: CatalogValue[],
  axis: string,
  label: string,
  seriesId: string | null
): CurveLine {
  const first = members[0]
  const points = members
    .map((one) => [numberAt(one, axis), one.value_num] as const)
    .filter((pair): pair is readonly [number, number] => pair[0] !== null && pair[1] != null)
    .map(([x, y]) => [x, y] as [number, number])
    .sort((left, right) => left[0] - right[0])
  return {
    id,
    propertyKey: first.property_key,
    name: first.property_name,
    unit: first.unit ?? null,
    axis,
    label,
    points,
    tier: Math.max(...members.map((one) => one.quality_tier)),
    source: first.source ?? null,
    seriesId,
  }
}

/**
 * **화면이 이은 선** — 같은 물성의 값 가운데 출처 · 방법 · 나머지 조건이 같고 수 조건 하나만
 * 다른 것을 그 축을 따라 잇는다. 한 값은 한 선에만 — 점이 많은 선부터 정한다(온도로도 속도로도
 * 이을 수 있으면 더 긴 쪽). 원본에서 빠진 값 · 계수 묶음의 항 · 직접 넣은 한 벌의 점은 뺀다.
 */
export function autoCurves(values: CatalogValue[]): CurveLine[] {
  const byKey = new Map<string, CatalogValue[]>()
  for (const value of values) {
    if (value.series_id || value.formula_term || value.source_missing_at) continue
    if (value.value_num === null || value.value_num === undefined) continue
    const list = byKey.get(value.property_key) ?? []
    list.push(value)
    byKey.set(value.property_key, list)
  }
  const lines: CurveLine[] = []
  for (const [key, list] of byKey) {
    if (list.length < MIN_CURVE_POINTS) continue
    const counts = new Map<string, number>()
    for (const value of list) {
      for (const axis of Object.keys((value.conditions as Record<string, unknown> | null) ?? {})) {
        if (canBeAxis(axis) && numberAt(value, axis) !== null) {
          counts.set(axis, (counts.get(axis) ?? 0) + 1)
        }
      }
    }
    const candidates: { axis: string; members: CatalogValue[] }[] = []
    for (const [axis, count] of counts) {
      if (count < MIN_CURVE_POINTS) continue
      const buckets = new Map<string, CatalogValue[]>()
      for (const value of list) {
        if (numberAt(value, axis) === null) continue
        const sig = signature(value, axis)
        const bucket = buckets.get(sig) ?? []
        bucket.push(value)
        buckets.set(sig, bucket)
      }
      for (const members of buckets.values()) {
        if (distinctX(members, axis) >= MIN_CURVE_POINTS) candidates.push({ axis, members })
      }
    }
    candidates.sort((left, right) => right.members.length - left.members.length)
    const used = new Set<string>()
    for (const candidate of candidates) {
      const free = candidate.members.filter((one) => !used.has(one.id))
      if (distinctX(free, candidate.axis) < MIN_CURVE_POINTS) continue
      for (const one of free) used.add(one.id)
      const rest = Object.fromEntries(
        Object.entries((free[0].conditions as Record<string, unknown> | null) ?? {}).filter(
          ([name]) => name !== candidate.axis && name !== 'assumption'
        )
      )
      lines.push(
        lineOf(`auto:${key}:${candidate.axis}:${lines.length}`, free, candidate.axis, fmtConditions(rest), null)
      )
    }
  }
  return lines
}

/** 직접 넣은 한 벌(곡선)의 열마다 선. 계수 묶음은 선이 아니다 — 「계수 묶음」 탭이 본다. */
export function seriesCurves(series: CatalogSeries[], values: CatalogValue[]): CurveLine[] {
  const lines: CurveLine[] = []
  for (const one of series) {
    if (one.kind !== 'curve' || !one.x_key) continue
    const mine = values.filter((value) => value.series_id === one.id)
    for (const column of one.columns) {
      const members = mine.filter((value) => value.property_key === column.property_key)
      if (members.length === 0) continue
      lines.push(lineOf(`series:${one.id}:${column.property_key}`, members, one.x_key, one.label, one.id))
    }
  }
  return lines
}

export interface ScatterSet {
  propertyKey: string
  name: string
  unit: string | null
  /** 파단 점 `[x(축 단위), y(SI)]`. */
  solid: [number, number][]
  /** 런아웃(멈춘 점) — 빈 점으로 그린다. 「여기서도 안 끝났다」 는 하한이다. */
  hollow: [number, number][]
}

/**
 * 직접 넣은 **산점 한 벌**(S-N · ε-N, ADR 0068)의 열마다 점 — 런아웃은 따로. 산점은 함수가 아니라
 * 잇지 않는다(이으면 지그재그가 돼 뜻이 없다).
 */
export function scatterSets(series: CatalogSeries, values: CatalogValue[]): ScatterSet[] {
  if (series.kind !== 'scatter' || !series.x_key) return []
  const axis = series.x_key
  const mine = values.filter((value) => value.series_id === series.id)
  return series.columns.map((column) => {
    const solid: [number, number][] = []
    const hollow: [number, number][] = []
    for (const value of mine) {
      if (value.property_key !== column.property_key || value.value_num == null) continue
      const x = numberAt(value, axis)
      if (x === null) continue
      const runout = (value.conditions as Record<string, unknown> | null)?.['runout'] === true
      ;(runout ? hollow : solid).push([x, value.value_num])
    }
    const byX = (left: [number, number], right: [number, number]) => left[0] - right[0]
    return {
      propertyKey: column.property_key,
      name: column.property_name,
      unit: column.unit ?? null,
      solid: solid.sort(byX),
      hollow: hollow.sort(byX),
    }
  })
}

export interface SourceRow {
  source: Source | null
  count: number
  properties: number
  tiers: number[]
  methods: string[]
}

/** 출처 하나에 한 줄 — 값이 많은 출처부터. 출처 없는 값이 있으면 그것도 한 줄로 선다. */
export function sourceRows(values: CatalogValue[]): SourceRow[] {
  const rows = new Map<string, { source: Source | null; values: CatalogValue[] }>()
  for (const value of values) {
    const id = value.source?.id ?? ''
    const row = rows.get(id) ?? { source: value.source ?? null, values: [] }
    row.values.push(value)
    rows.set(id, row)
  }
  return [...rows.values()]
    .map(({ source, values: list }) => ({
      source,
      count: list.length,
      properties: new Set(list.map((one) => one.property_key)).size,
      tiers: [...new Set(list.map((one) => one.quality_tier))].sort((a, b) => a - b),
      methods: [...new Set(list.map((one) => one.method ?? '').filter(Boolean))].sort(),
    }))
    .sort((left, right) => right.count - left.count)
}

/** 등급마다 값 수. */
export function tierCounts(values: CatalogValue[]): Map<number, number> {
  const counts = new Map<number, number>()
  for (const value of values) counts.set(value.quality_tier, (counts.get(value.quality_tier) ?? 0) + 1)
  return new Map([...counts].sort(([left], [right]) => left - right))
}
