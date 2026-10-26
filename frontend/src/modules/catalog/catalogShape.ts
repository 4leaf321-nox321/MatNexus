/**
 * 문헌 재료 상세를 **체계적으로 펴는 계산**(2026-10-22, ADR 0067) — 그리지 않고 모양만 만든다.
 *
 *   propertyGroups   물성 하나에 한 줄 — 대표값 · 값 수 · 등급 · 갈리는 조건의 범위
 *   autoCurves       같은 물성의 값이 조건축 하나로만 갈리면 그 축을 따라 이은 선. **저장된
 *                    묶음이 아니라 화면이 이은 것이다** — 이관해 온 값에는 묶음 id 가 없다
 *                    (사용자 결정 2026-10-22: 저장된 값은 그대로 두고 화면에서만 잇는다)
 *   seriesLines      직접 넣은 한 벌(곡선)의 열마다 선 — 그 벌의 점으로
 *   sourceRows       출처 하나에 한 줄 — 값 수 · 물성 수 · 등급
 *
 * 전에는 값 하나가 한 줄이라, 값이 366건인 재료(SAC-Q)는 같은 물성 이름이 수십 줄 섰고 그것이
 * 온도를 따라 이어진 한 곡선이라는 것은 조건 칸을 눈으로 대조해야 알았다.
 *
 * **곡선 · 산점의 점은 상세에 안 실린다**(ADR 0072) — 대표로 뽑힌 곡선 점만 값 목록에 온다.
 * 수 · 범위 · 등급은 벌 머리(`series`)에서 세고, 점은 그 벌을 펼칠 때 따로 받는다.
 */

import { fmtConditions, isBookkeeping } from '@/modules/catalog/api'
import { AXIS_META } from '@/modules/catalog/axisMeta'
import type { CatalogSeries, CatalogSeriesBrief, CatalogSeriesPoint, CatalogValue } from '@/modules/catalog/api'

type Source = NonNullable<CatalogValue['source']>

/** 선으로 이을 최소 점 수. 둘은 「값 둘」 이지 곡선이라 부르기 어렵다. */
export const MIN_CURVE_POINTS = 3

/** 축이 될 수 없는 조건 — 가정 표지 · 계수 묶음 표지. */
const NOT_AXIS = new Set(['assumption', 'model', 'set_id', 'n_terms'])

/**
 * 축 키 → [이름, 저장 단위] · 로그 축 — **문헌 조건 칸 목록(서버 씨앗)에서 만든 표**다(`axisMeta.ts`,
 * 2026-10-26). 전에는 여기 손으로 따로 적어, 서버 목록에 ΔK 를 더해도 화면은 키 이름을 그대로 보였다.
 * 모르는 축은 키 그대로 · 단위 없이 그린다.
 */
export { AXIS_META, LOG_AXES } from '@/modules/catalog/axisMeta'

/**
 * 값이 **두 자릿수 넘게** 걸치는가 — 그러면 세로도 자릿수로 그린다. 균열 성장률(da/dN)은
 * 10⁻¹⁰ ~ 10⁻⁶ m/cycle 에 걸쳐, 고른 눈금이면 마지막 점 하나만 보이고 나머지는 바닥에 붙는다.
 */
export function spansDecades(values: number[], decades = 2): boolean {
  if (values.length < 2 || values.some((one) => !(one > 0))) return false
  return Math.log10(Math.max(...values) / Math.min(...values)) > decades
}

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

/** 점이 상세에 안 실리는 벌(곡선 · 산점) — 계수 묶음의 항은 값 목록에 그대로 있다. */
export function pointSets<T extends CatalogSeriesBrief>(series: T[]): T[] {
  return series.filter((one) => one.kind === 'curve' || one.kind === 'scatter')
}

/** 값 목록 가운데 벌의 점이 아닌 것 — 점은 벌 머리의 수로 센다(대표로 실린 점을 두 번 세지 않게). */
function ownValues(values: CatalogValue[], series: CatalogSeriesBrief[]): CatalogValue[] {
  const ids = new Set(pointSets(series).map((one) => one.id))
  return values.filter((value) => !value.series_id || !ids.has(value.series_id))
}

/** 값 수 — 낱값 · 계수 항에 곡선 · 산점의 점까지. */
export function valueTotal(values: CatalogValue[], series: CatalogSeriesBrief[]): number {
  return (
    ownValues(values, series).length +
    pointSets(series).reduce((sum, one) => sum + one.point_count, 0)
  )
}

/** 직접 넣은 곡선의 선 수 — 열마다 하나(점이 있는 열만). 산점은 선이 아니다. */
export function seriesLineCount(series: CatalogSeriesBrief[], propertyKey?: string): number {
  return series
    .filter((one) => one.kind === 'curve' && one.x_key)
    .flatMap((one) => one.columns)
    .filter((column) => (column.count ?? 0) > 0)
    .filter((column) => propertyKey === undefined || column.property_key === propertyKey).length
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
  /** 값 목록에 실린 이 물성의 값 — 곡선 · 산점의 점은 대표로 뽑힌 것만. */
  values: CatalogValue[]
  /** 대표값 — 서버가 고른 대표, 없으면 첫 값. **산점만 있는 물성은 없다**(점은 대표가 아니다). */
  head: CatalogValue | null
  /** 값 수 — 곡선 · 산점의 점까지(점은 벌 머리에서 센다). */
  count: number
  /** 그중 곡선 · 산점의 점 — 값 목록에는 대표로 뽑힌 점만 있다. */
  points: number
  /** 이 물성의 산점 벌 수(S-N · ε-N). 산점은 선이 아니라 `curves` 에 안 든다. */
  scatters: number
  /** 등급들(오름차순, 겹치지 않게). */
  tiers: number[]
  /** 값마다 갈리는 수 조건의 범위 — 「온도 25~150 °C」. 벌의 축 범위도 든다. */
  ranges: AxisRange[]
  /** 계수 묶음의 항만 있는 물성(Anand 상수 …) — 낱값이 아니라 「계수 묶음」 탭에서 본다. */
  parameterized: boolean
  /** 이 물성의 선 수(입력한 곡선 + 화면이 이은 것). */
  curves: number
}

/**
 * 물성 하나에 한 줄. 서버가 준 차례(분야 → 물성, 대표 먼저)를 지킨다. 곡선 · 산점의 벌에만 있는
 * 물성은 뒤에 붙는다 — 벌 머리의 열(이름 · 점 수 · 범위)로. 요약 화면이 분야별로 다시 모은다.
 */
export function propertyGroups(
  values: CatalogValue[],
  autoLines: CurveLine[] = [],
  series: CatalogSeriesBrief[] = []
): PropertyGroup[] {
  const byKey = new Map<string, CatalogValue[]>()
  for (const value of values) {
    const list = byKey.get(value.property_key)
    if (list) list.push(value)
    else byKey.set(value.property_key, [value])
  }
  const own = new Set(ownValues(values, series).map((one) => one.id))
  const sets = pointSets(series)
  const columns = new Map<string, { set: CatalogSeriesBrief; column: CatalogSeriesBrief['columns'][number] }[]>()
  for (const set of sets) {
    for (const column of set.columns) {
      const list = columns.get(column.property_key) ?? []
      list.push({ set, column })
      columns.set(column.property_key, list)
    }
  }
  const autoCount = new Map<string, number>()
  for (const line of autoLines) autoCount.set(line.propertyKey, (autoCount.get(line.propertyKey) ?? 0) + 1)

  const keys = [...new Set([...byKey.keys(), ...columns.keys()])]
  return keys.map((key) => {
    const list = byKey.get(key) ?? []
    const mine = columns.get(key) ?? []
    const scalars = list.filter((one) => !one.formula_term)
    const head =
      scalars.find((one) => one.representative && !one.source_missing_at) ?? scalars[0] ?? list[0] ?? null
    const first = mine[0]?.column
    const points = mine.reduce((sum, one) => sum + (one.column.count ?? 0), 0)
    const ranges = mergeRanges([
      ...rangesOf(scalars),
      ...mine.flatMap(({ set }) =>
        set.x_key && set.x_min != null && set.x_max != null
          ? [{ key: set.x_key, min: set.x_min, max: set.x_max }]
          : []
      ),
    ])
    return {
      propertyKey: key,
      name: head?.property_name ?? first?.property_name ?? key,
      domain: head?.domain ?? first?.domain ?? '',
      symbol: head?.symbol ?? first?.symbol ?? null,
      values: list,
      head,
      count: list.filter((one) => own.has(one.id)).length + points,
      points,
      scatters: new Set(mine.filter(({ set }) => set.kind === 'scatter').map(({ set }) => set.id)).size,
      tiers: [...new Set([...list.map((one) => one.quality_tier), ...mine.map(({ set }) => set.quality_tier)])].sort(
        (a, b) => a - b
      ),
      ranges,
      parameterized: list.length > 0 && scalars.length === 0,
      curves: seriesLineCount(series, key) + (autoCount.get(key) ?? 0),
    }
  })
}

function rangesOf(values: CatalogValue[]): AxisRange[] {
  const out: AxisRange[] = []
  for (const value of values) {
    for (const key of Object.keys((value.conditions as Record<string, unknown> | null) ?? {})) {
      if (!canBeAxis(key)) continue
      const at = numberAt(value, key)
      if (at !== null) out.push({ key, min: at, max: at })
    }
  }
  return out
}

/** 같은 축의 범위를 하나로 — 한 값뿐이라 넓이가 없으면 뺀다. */
function mergeRanges(ranges: AxisRange[]): AxisRange[] {
  const seen = new Map<string, AxisRange>()
  for (const range of ranges) {
    const known = seen.get(range.key)
    seen.set(
      range.key,
      known
        ? { key: range.key, min: Math.min(known.min, range.min), max: Math.max(known.max, range.max) }
        : { ...range }
    )
  }
  return [...seen.values()].filter((range) => range.min !== range.max)
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

/**
 * 직접 넣은 한 벌(곡선)의 열마다 선 — 그 벌의 점(`GET /catalog/series/{id}/points`)으로. 계수
 * 묶음은 선이 아니다 — 「계수 묶음」 탭이 본다. 산점도 잇지 않는다(`scatterSets`).
 */
export function seriesLines(series: CatalogSeries, points: CatalogSeriesPoint[]): CurveLine[] {
  if (series.kind !== 'curve' || !series.x_key) return []
  const axis = series.x_key
  return series.columns.flatMap((column) => {
    const drawn = points
      .filter((point) => point.property_key === column.property_key && point.x != null)
      .map((point) => [point.x as number, point.value] as [number, number])
      .sort((left, right) => left[0] - right[0])
    if (drawn.length === 0) return []
    return [
      {
        id: `series:${series.id}:${column.property_key}`,
        propertyKey: column.property_key,
        name: column.property_name,
        unit: column.unit ?? null,
        axis,
        label: series.label,
        points: drawn,
        tier: series.quality_tier,
        source: series.source ?? null,
        seriesId: series.id,
      },
    ]
  })
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
export function scatterSets(series: CatalogSeries, points: CatalogSeriesPoint[]): ScatterSet[] {
  if (series.kind !== 'scatter' || !series.x_key) return []
  return series.columns.map((column) => {
    const solid: [number, number][] = []
    const hollow: [number, number][] = []
    for (const point of points) {
      if (point.property_key !== column.property_key || point.x == null) continue
      const runout = (point.row_conditions as Record<string, unknown> | null)?.['runout'] === true
      ;(runout ? hollow : solid).push([point.x, point.value])
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

/**
 * 출처 하나에 한 줄 — 값이 많은 출처부터. 출처 없는 값이 있으면 그것도 한 줄로 선다. 곡선 · 산점의
 * 점은 벌 머리로 센다(출처 · 등급 · 방법이 벌 전체로 하나다).
 */
export function sourceRows(values: CatalogValue[], series: CatalogSeriesBrief[] = []): SourceRow[] {
  const rows = new Map<
    string,
    { source: Source | null; count: number; properties: Set<string>; tiers: Set<number>; methods: Set<string> }
  >()
  function add(source: Source | null, count: number, keys: string[], tier: number, method: string | null) {
    const id = source?.id ?? ''
    const row = rows.get(id) ?? { source, count: 0, properties: new Set(), tiers: new Set(), methods: new Set() }
    row.count += count
    for (const key of keys) row.properties.add(key)
    row.tiers.add(tier)
    if (method) row.methods.add(method)
    rows.set(id, row)
  }
  for (const value of ownValues(values, series)) {
    add(value.source ?? null, 1, [value.property_key], value.quality_tier, value.method ?? null)
  }
  for (const set of pointSets(series)) {
    add(
      set.source ?? null,
      set.point_count,
      set.columns.map((column) => column.property_key),
      set.quality_tier,
      set.method
    )
  }
  return [...rows.values()]
    .map((row) => ({
      source: row.source,
      count: row.count,
      properties: row.properties.size,
      tiers: [...row.tiers].sort((a, b) => a - b),
      methods: [...row.methods].sort(),
    }))
    .sort((left, right) => right.count - left.count)
}

/** 등급마다 값 수 — 곡선 · 산점의 점까지. */
export function tierCounts(values: CatalogValue[], series: CatalogSeriesBrief[] = []): Map<number, number> {
  const counts = new Map<number, number>()
  const add = (tier: number, count: number) => counts.set(tier, (counts.get(tier) ?? 0) + count)
  for (const value of ownValues(values, series)) add(value.quality_tier, 1)
  for (const set of pointSets(series)) add(set.quality_tier, set.point_count)
  return new Map([...counts].sort(([left], [right]) => left - right))
}
