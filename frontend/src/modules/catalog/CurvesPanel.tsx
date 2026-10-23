/**
 * 「곡선 · 표」 탭 — **이어진 값을 선으로**(2026-10-22, ADR 0067).
 *
 *   직접 넣은 한 벌     `catalog_series` 에 저장된 곡선 · 표. 출처 · 등급 · 방법이 벌 전체로 하나다
 *   화면이 이은 선      저장된 묶음이 아니다 — 같은 물성의 값이 조건축 하나로만 갈리면 그 축을
 *                      따라 이었다(`catalogShape.autoCurves`). 이관해 온 값에는 묶음 id 가 없어서다
 *
 * 둘을 **다른 이름으로 세운다** — 화면이 이은 선을 저장된 곡선처럼 보이면, 숨은 조건(노화 · 시편)
 * 으로 갈렸어야 할 값이 한 선이라고 믿게 된다.
 *
 * **점은 벌을 펼칠 때 받는다**(ADR 0072). 재료 상세가 점을 다 실으면 벌 555개 · 점 9,105개인
 * 재료가 16 MB 였다. 앞의 몇 벌만 펼쳐 두고, 벌은 20개씩 세운다.
 */

import { ChevronDown, ChevronRight, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { catalogApi } from '@/modules/catalog/api'
import type { CatalogSeries, CatalogSeriesPoint } from '@/modules/catalog/api'
import { SourceLabel, TierBadge } from '@/modules/catalog/CatalogValueTable'
import { METHOD_LABELS } from '@/modules/catalog/catalogForms'
import {
  LOG_AXES,
  axisName,
  axisUnit,
  pointSets,
  scatterSets,
  seriesLines,
} from '@/modules/catalog/catalogShape'
import type { CurveLine } from '@/modules/catalog/catalogShape'
import { CurveChart } from '@/modules/tests/CurveChart'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel, formatScalar, toDisplay } from '@/shared/units'

/** 한 그래프에 겹칠 선의 상한 — 넘으면 앞의 것만 그리고 그렇다고 말한다. */
const MAX_LINES = 12

/** 처음부터 펼쳐 둘 벌 수 — 나머지는 머리만 서고, 펼치면 그때 점을 받는다. */
const OPEN_FIRST = 4

/** 한 번에 세울 벌 수 — 벌이 555개인 재료가 있다(2026-10-24). */
const PAGE = 20

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

const KIND_LABELS: Record<string, string> = { curve: '곡선 · 표', scatter: '산점' }

/**
 * **산점 한 벌**(S-N · ε-N) — 점을 잇지 않고, 런아웃은 빈 점으로(ADR 0068). 수명 축이면
 * 자릿수로 펼친다(log-log). 점 목록은 같은 x 가 여럿이라 줄마다 하나씩 보인다.
 */
function ScatterView({ series, points }: { series: CatalogSeries; points: CatalogSeriesPoint[] }) {
  const [table, setTable] = useState(false)
  const axis = series.x_key ?? ''
  const xUnit = axisUnit(axis)
  const sets = scatterSets(series, points)
  const log = LOG_AXES.has(axis)
  return (
    <div className="space-y-2">
      <div className="grid gap-3 lg:grid-cols-2">
        {sets.map((set) => {
          const shown = (point: [number, number]): [number, number] => [
            toDisplay(point[0], xUnit),
            toDisplay(point[1], set.unit),
          ]
          return (
            <CurveChart
              key={set.propertyKey}
              points={[]}
              pointsLabel={set.name}
              dots={[
                { points: set.solid.map(shown), label: '파단' },
                ...(set.hollow.length > 0
                  ? [{ points: set.hollow.map(shown), label: '런아웃', hollow: true }]
                  : []),
              ]}
              xLabel={axisLabel(axisName(axis), xUnit)}
              yLabel={axisLabel(set.name, set.unit)}
              logX={log}
              logY={log}
              height={260}
            />
          )
        })}
      </div>
      <button
        type="button"
        className="text-primary text-xs underline-offset-2 hover:underline"
        aria-expanded={table}
        onClick={() => setTable((current) => !current)}
      >
        {table ? '점 목록 접기' : '점 목록 보기'}
      </button>
      {table && (
        <div className="max-h-80 overflow-auto rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>{axisLabel(axisName(axis), xUnit)}</TableHead>
                <TableHead>물성</TableHead>
                <TableHead className="text-right">값</TableHead>
                <TableHead>런아웃</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sets.flatMap((set) =>
                [
                  ...set.solid.map((point) => ({ point, runout: false })),
                  ...set.hollow.map((point) => ({ point, runout: true })),
                ]
                  .sort((left, right) => left.point[0] - right.point[0])
                  .map(({ point, runout }, index) => (
                    <TableRow key={`${set.propertyKey}-${index}`}>
                      <TableCell className="tabular-nums">
                        {formatScalar(point[0], xUnit ?? undefined)}
                      </TableCell>
                      <TableCell>{set.name}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatScalar(point[1], set.unit ?? undefined)}
                      </TableCell>
                      <TableCell>{runout ? '런아웃' : ''}</TableCell>
                    </TableRow>
                  ))
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

/**
 * 직접 넣은 한 벌 — 머리 · 그래프(곡선이면) · 펼치는 표 · 지우기. 점은 펼칠 때 받는다(ADR 0072) —
 * 한 번 받으면 접었다 펴도 다시 받지 않는다.
 */
export function SeriesCard({
  series,
  canRemove,
  onRemove,
  initiallyOpen = true,
}: {
  series: CatalogSeries
  canRemove: boolean
  onRemove: (series: CatalogSeries) => void
  initiallyOpen?: boolean
}) {
  const [open, setOpen] = useState(initiallyOpen)
  const [wanted, setWanted] = useState(initiallyOpen)
  const [table, setTable] = useState(false)
  const loaded = useResource(
    () => (wanted ? catalogApi.seriesPoints(series.id) : Promise.resolve(null)),
    [series.id, wanted]
  )
  const points = loaded.data?.points ?? []
  const lines = seriesLines(series, points)
  const xUnit = series.x_key ? axisUnit(series.x_key) : null
  const xs = [...new Set(points.map((point) => point.x).filter((x): x is number => x != null))].sort(
    (left, right) => left - right
  )
  const at = (x: number, key: string) => points.find((point) => point.property_key === key && point.x === x)

  function toggle() {
    setOpen((current) => !current)
    setWanted(true)
  }

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="flex items-center gap-1 text-left font-medium hover:underline"
          aria-expanded={open}
          aria-label={`${series.label} ${open ? '접기' : '펼치기'}`}
          onClick={toggle}
        >
          {open ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
          <h3>{series.label}</h3>
        </button>
        <Badge variant="secondary">
          {KIND_LABELS[series.kind] ?? `계수 묶음 · ${series.model ?? ''}`}
        </Badge>
        {series.batch_key && (
          <Badge variant="outline" title="외부 공개 데이터 반입 묶음으로 들어온 한 벌입니다">
            반입 · {series.batch_key}
          </Badge>
        )}
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
      {open && body()}
    </div>
  )

  function body() {
    if (loaded.error) return <ErrorNotice error={loaded.error} />
    if (!loaded.data) return <p className="text-muted-foreground text-xs">점을 받는 중…</p>
    return (
      <>
        {series.kind === 'scatter' && <ScatterView series={series} points={points} />}
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
                              {point ? formatScalar(point.value, column.unit ?? undefined) : '—'}
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
            {points.map((point, index) => (
              <li key={`${point.property_key}-${point.term ?? index}`} className="tabular-nums">
                <span className="font-medium">{point.term ?? point.property_key}</span> = {point.value}
                {point.term_unit && point.term_unit !== '1' ? ` ${point.term_unit}` : ''}
                {!point.term_unit && point.unit && point.unit !== '1' ? ` ${point.unit}` : ''}
              </li>
            ))}
          </ul>
        )}
      </>
    )
  }
}

export function CurvesPanel({
  series,
  autoLines,
  canRemove,
  onRemove,
}: {
  series: CatalogSeries[]
  autoLines: CurveLine[]
  canRemove: (series: CatalogSeries) => boolean
  onRemove: (series: CatalogSeries) => void
}) {
  const curves = pointSets(series)
  const [shown, setShown] = useState(PAGE)
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
          직접 넣은 곡선 · 표 · 산점
          <span className="text-muted-foreground ml-2 text-xs font-normal">{curves.length}벌</span>
        </h2>
        {curves.length === 0 ? (
          <p className="text-muted-foreground rounded-md border py-6 text-center text-sm">
            아직 없습니다. 「곡선 입력」 으로 문헌의 곡선 · 표를 한 벌로 넣을 수 있습니다.
          </p>
        ) : (
          <>
            {curves.length > OPEN_FIRST && (
              <p className="text-muted-foreground text-xs">
                앞의 {OPEN_FIRST}벌만 펼쳐 두었습니다 — 나머지는 이름을 누르면 점을 받아 그립니다.
              </p>
            )}
            {curves.slice(0, shown).map((one, index) => (
              <SeriesCard
                key={one.id}
                series={one}
                canRemove={canRemove(one)}
                onRemove={onRemove}
                initiallyOpen={index < OPEN_FIRST}
              />
            ))}
            {curves.length > shown && (
              <Button size="sm" variant="outline" onClick={() => setShown((current) => current + PAGE)}>
                더 보기 (남은 {curves.length - shown}벌)
              </Button>
            )}
          </>
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
