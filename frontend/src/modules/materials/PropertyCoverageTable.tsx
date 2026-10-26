/**
 * 물성 지도 — **이 재료에 어떤 물성이 어떤 조건에 어떤 등급으로 있나, 한 장.**
 *
 * 시험으로 잰 값 · 사람이 적은 선언 · 이어진 문헌값을 물성 하나 아래 같은 줄 모양으로 편다.
 * 전에는 세 곳을 각자 열어 봐야 했다. 공용어(문헌 물성 키)에 안 이어진 스칼라·항목은
 * 「안 이어진 것」 으로 함께 보인다 — 지도에서 사라지면 없는 줄 안다.
 *
 * **문헌 곡선 · 산점 한 벌은 한 줄**이다(점 수 · 값 범위 · 조건 범위). 「점 펼치기」 를 누르면 그
 * 벌의 점을 받아 그 아래에 편다 — 1~몇 점짜리 산점이 수백 벌인 재료는 점마다 한 줄이면 지도가
 * 칸 7천 개였다(2026-10-26).
 *
 * 값은 SI 로 오고 표는 표시 단위로 바꿔 보인다(`shared/units`). 등급은 문헌·사내가 같은
 * 1~4 척도다 — 1 이 가장 좋다.
 */

import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { CoverageEntry, CoverageSeriesPoints, PropertyCoverage } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

const ORIGIN_LABEL: Record<string, string> = {
  measured: '시험',
  internal: '선언',
  catalog: '문헌',
}

const SERIES_KIND_LABEL: Record<string, string> = {
  curve: '곡선',
  scatter: '산점',
}

const CONDITION_LABEL: Record<string, string> = {
  temperature: '온도',
  strain_rate: '변형률속도',
  frequency: '주파수',
  humidity: '상대습도',
  pressure: '압력',
  crosshead_speed: '속도',
  preload: '예하중',
  aging_time: '노화 시간',
}

/** 표준 조건 키 → 저장 단위(SI). 표시 단위·환산은 `shared/units` 표가 정한다. */
const CONDITION_SI: Record<string, string> = {
  temperature: 'K',
  strain_rate: '1/s',
  frequency: 'Hz',
  humidity: '1',
  pressure: 'Pa',
  crosshead_speed: 'm/s',
  preload: 'N',
  aging_time: 's',
}

/** 「108.8~220.4 MPa」 — 두 끝의 단위가 같으면 한 번만 적는다. */
function rangeText(low: number, high: number, unit: string | null | undefined): string {
  const left = formatScalar(low, unit)
  const right = formatScalar(high, unit)
  if (left === right) return left
  const space = right.indexOf(' ')
  const suffix = space >= 0 ? right.slice(space) : ''
  return suffix && left.endsWith(suffix) ? `${left.slice(0, -suffix.length)}~${right}` : `${left}~${right}`
}

/** 조건을 사람 말로 — 모든 점이 같은 조건, 점마다 갈리는 조건의 범위, 표준 조건이 아닌 축. */
function conditionText(entry: CoverageEntry): string {
  const label = (key: string) => CONDITION_LABEL[key] ?? key
  const parts = Object.entries(entry.conditions).map(
    ([key, value]) => `${label(key)} ${formatScalar(value, CONDITION_SI[key])}`
  )
  for (const [key, [low, high]] of Object.entries(entry.condition_ranges ?? {})) {
    parts.push(`${label(key)} ${rangeText(low, high, CONDITION_SI[key])}`)
  }
  if (entry.axis_label && entry.axis_low != null && entry.axis_high != null) {
    parts.push(`${entry.axis_label} ${rangeText(entry.axis_low, entry.axis_high, entry.axis_unit)}`)
  }
  return parts.join(' · ')
}

function valueText(entry: CoverageEntry, siUnit: string | null): string {
  if (entry.series_id && entry.low_si != null && entry.high_si != null) {
    return siUnit ? rangeText(entry.low_si, entry.high_si, siUnit) : `${entry.low_si}~${entry.high_si}`
  }
  return siUnit ? formatScalar(entry.value_si, siUnit) : `${entry.value_si}`
}

type Opened = { error: Error | null; data: CoverageSeriesPoints | null }

type Line =
  | { kind: 'entry'; entry: CoverageEntry }
  | { kind: 'point'; entry: CoverageEntry }
  | { kind: 'note'; text: string; error?: Error | null }

/** 물성 하나 — 이름 칸이 그 아래 줄 전부(펼친 점까지)에 걸친다. */
function PropertyBlock({
  materialId,
  row,
}: {
  materialId: string
  row: PropertyCoverage['properties'][number]
}) {
  const [opened, setOpened] = useState<Record<string, Opened>>({})
  const [open, setOpen] = useState<Set<string>>(new Set())

  function toggle(seriesId: string) {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(seriesId)) next.delete(seriesId)
      else next.add(seriesId)
      return next
    })
    if (opened[seriesId]) return
    setOpened((current) => ({ ...current, [seriesId]: { error: null, data: null } }))
    materialsApi.coverageSeries(materialId, seriesId).then(
      (data) => setOpened((current) => ({ ...current, [seriesId]: { error: null, data } })),
      (caught: unknown) =>
        setOpened((current) => ({
          ...current,
          [seriesId]: {
            error: caught instanceof Error ? caught : new Error('점을 받지 못했습니다.'),
            data: null,
          },
        }))
    )
  }

  const lines: Line[] = []
  for (const entry of row.entries) {
    lines.push({ kind: 'entry', entry })
    const id = entry.series_id
    if (!id || !open.has(id)) continue
    const got = opened[id]
    if (got?.error) {
      lines.push({ kind: 'note', text: '', error: got.error })
    } else if (!got?.data) {
      lines.push({ kind: 'note', text: '점을 받는 중…' })
    } else {
      const points = got.data.properties.find((one) => one.key === row.key)?.entries ?? []
      for (const point of points) lines.push({ kind: 'point', entry: point })
      if (got.data.shown < got.data.total) {
        lines.push({
          kind: 'note',
          text: `점 ${got.data.total}개 중 ${got.data.shown}개를 고르게 골라 보였습니다 — 전부는 문헌 재료의 「곡선 · 표」 탭에 있습니다.`,
        })
      }
    }
  }

  return (
    <>
      {lines.map((line, index) => (
        <TableRow key={lineKey(line, index)}>
          {index === 0 && (
            <TableCell rowSpan={lines.length} className="align-top font-medium">
              {row.name}
            </TableCell>
          )}
          {line.kind === 'note' ? (
            <TableCell colSpan={5} className="text-muted-foreground pl-8">
              {line.error ? <ErrorNotice error={line.error} /> : line.text}
            </TableCell>
          ) : (
            <EntryCells
              entry={line.entry}
              siUnit={row.si_unit}
              nested={line.kind === 'point'}
              open={!!line.entry.series_id && open.has(line.entry.series_id)}
              onToggle={toggle}
            />
          )}
        </TableRow>
      ))}
    </>
  )
}

function lineKey(line: Line, index: number): string {
  if (line.kind === 'note') return `note-${index}`
  return `${line.kind}-${line.entry.ref_kind}-${line.entry.ref_id}-${index}`
}

function EntryCells({
  entry,
  siUnit,
  nested,
  open,
  onToggle,
}: {
  entry: CoverageEntry
  siUnit: string | null
  nested: boolean
  open: boolean
  onToggle: (seriesId: string) => void
}) {
  const conditions = conditionText(entry)
  const seriesId = entry.series_id
  return (
    <>
      <TableCell className={nested ? 'pl-8' : undefined}>
        {nested ? (
          <span className="text-muted-foreground">점</span>
        ) : (
          <Badge variant={entry.origin === 'measured' ? 'default' : 'secondary'}>
            {ORIGIN_LABEL[entry.origin] ?? entry.origin}
          </Badge>
        )}
      </TableCell>
      <TableCell className="tabular-nums">등급 {entry.tier}</TableCell>
      <TableCell className="tabular-nums">
        {valueText(entry, siUnit)}
        {entry.count > 1 && (
          <span className="text-muted-foreground">
            {' '}
            · {seriesId ? '점' : '표본'} {entry.count}
          </span>
        )}
      </TableCell>
      <TableCell>
        {conditions || <span className="text-muted-foreground">조건 없음</span>}
      </TableCell>
      <TableCell>
        {!nested && <span>{entry.ref_label}</span>}
        {seriesId && (
          <span>
            {' '}
            · {SERIES_KIND_LABEL[entry.series_kind ?? ''] ?? '한 벌'} 「{entry.series_label}」
          </span>
        )}
        {entry.method && (
          <span className="text-muted-foreground">
            {nested ? '' : ' · '}
            {entry.method}
          </span>
        )}
        {seriesId && (
          <button
            type="button"
            className="text-primary ml-2 inline-flex items-center gap-0.5 underline-offset-2 hover:underline"
            aria-expanded={open}
            onClick={() => onToggle(seriesId)}
          >
            {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
            {open ? '점 접기' : `점 펼치기 (${entry.count})`}
          </button>
        )}
      </TableCell>
    </>
  )
}

export function PropertyCoverageTable({ materialId }: { materialId: string }) {
  const coverage = useResource<PropertyCoverage>(
    () => materialsApi.propertyCoverage(materialId),
    [materialId],
  )
  const data = coverage.data
  const unmapped = data
    ? [...(data.unmapped.scalars ?? []), ...(data.unmapped.items ?? [])]
    : []

  return (
    <section className="space-y-3">
      <p className="text-muted-foreground text-xs">
        시험으로 잰 값 · 적어 둔 값 · 이어진 문헌값을 물성마다 한 줄씩. 문헌의 곡선 · 산점은 한 벌이
        한 줄이고 「점 펼치기」 로 점을 봅니다. 등급은 1 이 가장 좋습니다(실측·표본 3 이상) — 문헌과
        같은 척도입니다.
      </p>
      <ErrorNotice error={coverage.error} />
      {data && data.properties.length === 0 && (
        <p className="text-muted-foreground rounded-md border py-6 text-center text-sm">
          이 재료에는 아직 값이 없습니다 — 시험을 등록하거나 재료 기본 정보 카드로 적어
          넣으면 여기 섭니다.
        </p>
      )}
      {data && data.properties.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>물성</TableHead>
                <TableHead>출처</TableHead>
                <TableHead>등급</TableHead>
                <TableHead>값</TableHead>
                <TableHead>조건</TableHead>
                <TableHead>어디서</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.properties.map((row) => (
                <PropertyBlock key={row.key} materialId={materialId} row={row} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {unmapped.length > 0 && (
        <p className="text-muted-foreground text-xs" data-testid="coverage-unmapped">
          공용어에 안 이어져 지도에 못 선 것: {unmapped.join(', ')} — 온톨로지 편집 &gt; 물성 매핑에서
          이으면 보입니다.
        </p>
      )}
    </section>
  )
}
