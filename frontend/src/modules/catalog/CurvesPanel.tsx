/**
 * 「곡선 · 표」 탭 — **이어진 값을 선으로**(2026-10-22, ADR 0067).
 *
 *   직접 넣은 한 벌     `catalog_series` 에 저장된 곡선 · 표. 출처 · 등급 · 방법이 벌 전체로 하나다
 *   화면이 이은 선      저장된 묶음이 아니다 — 같은 물성의 값이 조건축 하나로만 갈리면 그 축을
 *                      따라 이었다(`catalogShape.autoCurves`). 이관해 온 값에는 묶음 id 가 없어서다
 *
 * 둘을 **다른 이름으로 세운다** — 화면이 이은 선을 저장된 곡선처럼 보이면, 숨은 조건(노화 · 시편)
 * 으로 갈렸어야 할 값이 한 선이라고 믿게 된다.
 */

import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { CatalogSeries, CatalogValue } from '@/modules/catalog/api'
import { SourceLabel, TierBadge } from '@/modules/catalog/CatalogValueTable'
import { METHOD_LABELS } from '@/modules/catalog/catalogForms'
import { LOG_AXES, axisName, axisUnit } from '@/modules/catalog/catalogShape'
import type { CurveLine } from '@/modules/catalog/catalogShape'
import { CurveChart } from '@/modules/tests/CurveChart'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { axisLabel, formatScalar, toDisplay } from '@/shared/units'

/** 한 그래프에 겹칠 선의 상한 — 넘으면 앞의 것만 그리고 그렇다고 말한다. */
const MAX_LINES = 12

/** 겹친 선의 색 — 첫 선은 그래프의 기본색, 나머지는 이 차례로. 범례의 칸도 같은 색이다. */
const TONES = [
  { stroke: 'stroke-amber-600 dark:stroke-amber-400', swatch: 'bg-amber-600 dark:bg-amber-400' },
  { stroke: 'stroke-emerald-600 dark:stroke-emerald-400', swatch: 'bg-emerald-600 dark:bg-emerald-400' },
  { stroke: 'stroke-rose-600 dark:stroke-rose-400', swatch: 'bg-rose-600 dark:bg-rose-400' },
  { stroke: 'stroke-violet-600 dark:stroke-violet-400', swatch: 'bg-violet-600 dark:bg-violet-400' },
  { stroke: 'stroke-slate-500 dark:stroke-slate-400', swatch: 'bg-slate-500 dark:bg-slate-400' },
  { stroke: 'stroke-sky-600 dark:stroke-sky-400', swatch: 'bg-sky-600 dark:bg-sky-400' },
]

function shown(line: CurveLine): [number, number][] {
  const xUnit = axisUnit(line.axis)
  return line.points.map(([x, y]) => [toDisplay(x, xUnit), toDisplay(y, line.unit)])
}

/** 선 여럿을 한 판에 — 같은 물성 · 같은 축인 것만 모아 온다. */
function LinesChart({ lines }: { lines: CurveLine[] }) {
  const drawn = lines.slice(0, MAX_LINES)
  const [first, ...rest] = drawn
  const axis = first.axis
  const logX = LOG_AXES.has(axis) && drawn.every((line) => line.points.every(([x]) => x > 0))
  return (
    <div className="space-y-1">
      <CurveChart
        points={shown(first)}
        pointsLabel={first.label || first.name}
        background={rest.map((line, index) => ({
          points: shown(line),
          label: line.label || line.name,
          tone: TONES[index % TONES.length].stroke,
        }))}
        xLabel={axisLabel(axisName(axis), axisUnit(axis))}
        yLabel={axisLabel(first.name, first.unit)}
        logX={logX}
        height={260}
      />
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {drawn.map((line, index) => (
          <li key={line.id} className="flex items-center gap-1.5">
            <span
              className={`inline-block h-0.5 w-5 ${index === 0 ? 'bg-primary' : TONES[(index - 1) % TONES.length].swatch}`}
            />
            <span>{line.label || '조건 같음'}</span>
            <span className="text-muted-foreground">
              · {line.points.length}점 · {line.source?.title ?? '출처 없음'}
            </span>
          </li>
        ))}
      </ul>
      {lines.length > drawn.length && (
        <p className="text-muted-foreground text-xs">
          선이 {lines.length}개라 앞의 {MAX_LINES}개만 그렸습니다. 나머지는 「전체 값」 탭에 있습니다.
        </p>
      )}
    </div>
  )
}

/** 직접 넣은 한 벌 — 머리 · 그래프(곡선이면) · 펼치는 표 · 지우기. */
export function SeriesCard({
  series,
  values,
  lines,
  canRemove,
  onRemove,
}: {
  series: CatalogSeries
  values: CatalogValue[]
  lines: CurveLine[]
  canRemove: boolean
  onRemove: (series: CatalogSeries) => void
}) {
  const [table, setTable] = useState(false)
  const mine = values.filter((value) => value.series_id === series.id)
  const xUnit = series.x_key ? axisUnit(series.x_key) : null
  const xs = series.x_key
    ? [
        ...new Set(
          mine
            .map((value) => (value.conditions as Record<string, unknown> | null)?.[series.x_key ?? ''])
            .filter((x): x is number => typeof x === 'number')
        ),
      ].sort((left, right) => left - right)
    : []
  const at = (x: number, key: string) =>
    mine.find(
      (value) =>
        value.property_key === key &&
        (value.conditions as Record<string, unknown> | null)?.[series.x_key ?? ''] === x
    )
  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">{series.label}</h3>
        <Badge variant="secondary">{series.kind === 'curve' ? '곡선 · 표' : `계수 묶음 · ${series.model ?? ''}`}</Badge>
        <TierBadge tier={series.quality_tier} />
        <Badge variant="outline">{METHOD_LABELS[series.method] ?? series.method}</Badge>
        <span className="text-muted-foreground text-xs">
          점 {series.point_count}
          {series.created_by ? ` · 직접 넣음 · ${series.created_by}` : ''}
        </span>
        {canRemove && (
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive ml-auto h-7"
            aria-label={`${series.label} 묶음 삭제`}
            onClick={() => onRemove(series)}
          >
            <Trash2 className="size-3.5" />
            지우기
          </Button>
        )}
      </div>
      <SourceLabel source={series.source ?? null} detail={series.source_detail} />
      {lines.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          {lines.map((line) => (
            <LinesChart key={line.id} lines={[{ ...line, label: line.name }]} />
          ))}
        </div>
      )}
      {series.kind === 'curve' && series.x_key && (
        <>
          <button
            type="button"
            className="text-primary text-xs underline-offset-2 hover:underline"
            aria-expanded={table}
            onClick={() => setTable((current) => !current)}
          >
            {table ? '표 접기' : '표 보기'}
          </button>
          {table && (
            <div className="max-h-80 overflow-auto rounded-md border">
              <Table className="text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>{axisLabel(axisName(series.x_key), xUnit)}</TableHead>
                    {series.columns.map((column) => (
                      <TableHead key={column.property_key} className="text-right">
                        {axisLabel(column.property_name, column.unit)}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {xs.map((x) => (
                    <TableRow key={x}>
                      <TableCell className="tabular-nums">{formatScalar(x, xUnit ?? undefined)}</TableCell>
                      {series.columns.map((column) => {
                        const point = at(x, column.property_key)
                        return (
                          <TableCell key={column.property_key} className="text-right tabular-nums">
                            {point?.value_num == null ? '—' : formatScalar(point.value_num, column.unit ?? undefined)}
                          </TableCell>
                        )
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
      {series.kind === 'parameter_set' && (
        <ul className="grid gap-x-6 gap-y-0.5 text-sm sm:grid-cols-3">
          {mine.map((value) => (
            <li key={value.id} className="tabular-nums">
              <span className="font-medium">{value.term ?? value.property_name}</span> = {value.value_num}
              {value.term_unit && value.term_unit !== '1' ? ` ${value.term_unit}` : ''}
              {!value.term_unit && value.unit && value.unit !== '1' ? ` ${value.unit}` : ''}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function CurvesPanel({
  series,
  values,
  seriesLines,
  autoLines,
  canRemove,
  onRemove,
}: {
  series: CatalogSeries[]
  values: CatalogValue[]
  seriesLines: CurveLine[]
  autoLines: CurveLine[]
  canRemove: (series: CatalogSeries) => boolean
  onRemove: (series: CatalogSeries) => void
}) {
  const curves = series.filter((one) => one.kind === 'curve')
  // 화면이 이은 선은 물성 · 축마다 한 판에.
  const panels = new Map<string, CurveLine[]>()
  for (const line of autoLines) {
    const key = `${line.propertyKey}|${line.axis}`
    const list = panels.get(key) ?? []
    list.push(line)
    panels.set(key, list)
  }
  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">
          직접 넣은 곡선 · 표
          <span className="text-muted-foreground ml-2 text-xs font-normal">{curves.length}벌</span>
        </h2>
        {curves.length === 0 ? (
          <p className="text-muted-foreground rounded-md border py-6 text-center text-sm">
            아직 없습니다. 「곡선 입력」 으로 문헌의 곡선 · 표를 한 벌로 넣을 수 있습니다.
          </p>
        ) : (
          curves.map((one) => (
            <SeriesCard
              key={one.id}
              series={one}
              values={values}
              lines={seriesLines.filter((line) => line.seriesId === one.id)}
              canRemove={canRemove(one)}
              onRemove={onRemove}
            />
          ))
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">
          조건별 값을 이어 그림 (자동)
          <span className="text-muted-foreground ml-2 text-xs font-normal">선 {autoLines.length}</span>
        </h2>
        <p className="text-muted-foreground text-xs">
          저장된 곡선이 아니라, 같은 물성 · 출처 · 방법의 값 가운데 조건 하나(온도 · 속도 등)만 다른 것을
          화면이 그 조건을 따라 이은 것입니다. 숨은 조건이 있으면 실제로는 다른 곡선일 수 있습니다.
        </p>
        {panels.size === 0 ? (
          <p className="text-muted-foreground rounded-md border py-6 text-center text-sm">
            조건 하나로만 갈리는 값이 3개 이상인 물성이 없습니다.
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {[...panels.entries()].map(([key, lines]) => (
              <div key={key} className="space-y-1 rounded-md border p-3">
                <h3 className="text-sm font-medium">
                  {lines[0].name}
                  <span className="text-muted-foreground ml-2 text-xs font-normal">
                    축 {axisName(lines[0].axis)} · 선 {lines.length}
                  </span>
                </h3>
                <LinesChart lines={lines} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
