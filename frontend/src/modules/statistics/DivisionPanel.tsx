/**
 * 사업부별 현황 — **왼쪽 표, 오른쪽 연간 그래프.**
 *
 * 사업부는 시험에만 붙는다(ADR 0010 의 축). 재료·시편에는 사업부 칸이 없으므로
 * 여기의 재료·시료·시편 수는 **그 사업부의 시험이 걸친 것**이다 — 같은 재료를 두
 * 사업부가 시험하는 것이 정상이라, 열끼리 합치면 전체보다 클 수 있다.
 *
 * 순서는 서버가 정한다(MX · VD · DA · NW · 의료기기 — 실사용 요청으로 고정).
 * 「미지정」 이 보이면 그건 채울 일이 남았다는 뜻이다 — 숨기지 않는다.
 */

import type { DivisionOverview } from '@/modules/statistics/api'
import { Skeleton } from '@/shared/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

/** 사업부 색. 순서는 서버가 주는 순서 그대로 쓰고, 색만 여기서 돌려 쓴다. */
const PALETTE = ['#2563eb', '#16a34a', '#f59e0b', '#9333ea', '#dc2626', '#0891b2']
const UNSET_COLOR = '#9ca3af'

function colorOf(division: string, order: string[]): string {
  if (division === '미지정') return UNSET_COLOR
  const at = order.indexOf(division)
  return PALETTE[(at >= 0 ? at : order.length) % PALETTE.length]
}

export function DivisionPanel({
  data,
  loading,
}: {
  data: DivisionOverview | null
  loading: boolean
}) {
  if (loading && !data) return <Skeleton className="h-40" />
  if (!data || data.divisions.length === 0) return null

  const order = data.divisions.map((row) => row.division)

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">사업부별 현황</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>사업부</TableHead>
                  <TableHead className="text-right">재료</TableHead>
                  <TableHead className="text-right">시료</TableHead>
                  <TableHead className="text-right">시편</TableHead>
                  <TableHead className="text-right">시험</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.divisions.map((row) => (
                  <TableRow key={row.division}>
                    <TableCell
                      className={
                        row.division === '미지정' ? 'text-muted-foreground' : 'font-medium'
                      }
                    >
                      <span
                        className="mr-1.5 inline-block size-2 rounded-full align-middle"
                        style={{ backgroundColor: colorOf(row.division, order) }}
                      />
                      {row.division}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.material_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.sample_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.specimen_count}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.run_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            재료·시료·시편은 그 사업부의 시험이 걸친 수 — 같은 재료를 여러 사업부가 시험할
            수 있어 합계가 전체보다 클 수 있습니다.
          </p>
        </div>
        <YearChart data={data} order={order} />
      </div>
    </section>
  )
}

/** 연도 × 사업부 시험 수 — 묶음 막대. 라이브러리 없이 SVG 로 그린다(곡선 차트와 같다). */
function YearChart({ data, order }: { data: DivisionOverview; order: string[] }) {
  const years = [...new Set(data.yearly.map((row) => row.year))].sort()
  if (years.length === 0) {
    return <p className="text-muted-foreground self-center text-sm">아직 시험이 없습니다.</p>
  }
  const byYear = new Map<number, Map<string, number>>()
  for (const row of data.yearly) {
    if (!byYear.has(row.year)) byYear.set(row.year, new Map())
    byYear.get(row.year)?.set(row.division, row.run_count)
  }
  const top = Math.max(...data.yearly.map((row) => row.run_count), 1)

  const HEIGHT = 180
  const AXIS = 24
  const plot = HEIGHT - AXIS
  const groupWidth = 100 / years.length
  const barWidth = Math.min(groupWidth / (order.length + 1), 8)

  return (
    <div>
      <svg
        viewBox={`0 0 100 ${HEIGHT}`}
        preserveAspectRatio="none"
        className="h-44 w-full rounded-md border"
        role="img"
        aria-label="연도별 · 사업부별 시험 수"
      >
        {/* 눈금 — 0 · 절반 · 최대 */}
        {[0, 0.5, 1].map((step) => (
          <line
            key={step}
            x1={0}
            x2={100}
            y1={plot - plot * step}
            y2={plot - plot * step}
            stroke="currentColor"
            strokeOpacity={0.1}
            strokeWidth={0.4}
          />
        ))}
        {years.map((year, yi) => {
          const counts = byYear.get(year)
          const present = order.filter((division) => (counts?.get(division) ?? 0) > 0)
          const span = present.length * barWidth
          const start = groupWidth * yi + (groupWidth - span) / 2
          return (
            <g key={year}>
              {present.map((division, di) => {
                const count = counts?.get(division) ?? 0
                const barHeight = (count / top) * (plot - 12)
                return (
                  <rect
                    key={division}
                    x={start + di * barWidth + 0.5}
                    y={plot - barHeight}
                    width={barWidth - 1}
                    height={barHeight}
                    fill={colorOf(division, order)}
                  >
                    <title>{`${year} ${division}: ${count}건`}</title>
                  </rect>
                )
              })}
              <text
                x={groupWidth * yi + groupWidth / 2}
                y={HEIGHT - 8}
                textAnchor="middle"
                fontSize={9}
                fill="currentColor"
                opacity={0.7}
              >
                {year}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {order.map((division) => (
          <span key={division} className="text-muted-foreground inline-flex items-center gap-1">
            <span
              className="inline-block size-2 rounded-full"
              style={{ backgroundColor: colorOf(division, order) }}
            />
            {division}
          </span>
        ))}
        <span className="text-muted-foreground/70 ml-auto">연간 시험 수 (최대 {top}건)</span>
      </div>
    </div>
  )
}
