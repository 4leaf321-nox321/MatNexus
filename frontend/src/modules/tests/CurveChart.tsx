/**
 * 곡선 차트 — SVG 직접 그린다.
 *
 * **차트 라이브러리를 쓰지 않는 이유.** 계획서는 Recharts 를 후보로 두고 "Phase 2
 * 에서 실데이터로 확정" 하기로 했다. 실데이터를 보고 내린 결론은 지금은 필요
 * 없다는 것이다.
 *
 *   - 서버가 이미 LTTB 로 1200점 이하로 줄여 보낸다. 차트 라이브러리의 가장 큰
 *     값인 대용량 렌더링 최적화가 쓸 데가 없다.
 *   - 지금 필요한 것은 선 하나 · 축 두 개 · 값 읽기뿐이다. Recharts 는 gzip
 *     기준 100KB 가까이 되는데, 현재 번들 전체가 157KB 다. 곱절 가까이 늘리기에는
 *     얻는 것이 적다(§8.5 번들 예산).
 *
 * 다중 곡선 겹쳐 보기·브러시 확대·로그축이 필요해지는 Phase 3 에서 다시 판단한다.
 * 그때는 라이브러리가 값을 한다.
 *
 * 점은 **표시 단위로 이미 환산된 것**을 받는다. 이 컴포넌트는 단위를 모른다 —
 * 알면 SI 변환 규칙이 화면에도 생겨 두 곳이 된다.
 */

import { useMemo, useState } from 'react'

export interface CurveChartProps {
  points: [number, number][]
  xLabel: string
  yLabel: string
  height?: number
}

const PAD = { top: 16, right: 20, bottom: 44, left: 68 }
const WIDTH = 760

/** 사람이 읽기 좋은 눈금 간격 (1 · 2 · 5 × 10^n). */
function niceStep(span: number, count: number): number {
  const rough = span / count
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const normalized = rough / magnitude
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return step * magnitude
}

function ticks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [min]
  const step = niceStep(max - min, count)
  const start = Math.ceil(min / step) * step
  const result: number[] = []
  for (let value = start; value <= max + step * 1e-6; value += step) result.push(value)
  return result
}

function format(value: number): string {
  const magnitude = Math.abs(value)
  if (magnitude === 0) return '0'
  if (magnitude >= 10000 || magnitude < 0.001) return value.toExponential(2)
  return Number(value.toPrecision(4)).toString()
}

export function CurveChart({ points, xLabel, yLabel, height = 380 }: CurveChartProps) {
  const [hover, setHover] = useState<number | null>(null)

  const scale = useMemo(() => {
    if (points.length === 0) return null
    const xs = points.map((p) => p[0])
    const ys = points.map((p) => p[1])
    const xMin = Math.min(...xs)
    const xMax = Math.max(...xs)
    const yMin = Math.min(0, ...ys) // 하중·응력은 0 부터 보는 것이 실무 감각이다
    const yMax = Math.max(...ys)
    const xSpan = xMax - xMin || 1
    const ySpan = yMax - yMin || 1
    const plotWidth = WIDTH - PAD.left - PAD.right
    const plotHeight = height - PAD.top - PAD.bottom
    return {
      xMin,
      xMax,
      yMin,
      yMax,
      toX: (value: number) => PAD.left + ((value - xMin) / xSpan) * plotWidth,
      toY: (value: number) => PAD.top + plotHeight - ((value - yMin) / ySpan) * plotHeight,
      plotWidth,
      plotHeight,
    }
  }, [points, height])

  if (!scale) {
    return (
      <div
        className="text-muted-foreground flex items-center justify-center rounded-md border text-sm"
        style={{ height }}
      >
        그릴 점이 없습니다.
      </div>
    )
  }

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${scale.toX(p[0])},${scale.toY(p[1])}`).join(' ')
  const active = hover === null ? null : points[hover]

  return (
    <div className="rounded-md border p-2">
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="w-full"
        role="img"
        aria-label={`${yLabel} 대 ${xLabel} 곡선`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect()
          const svgX = ((event.clientX - box.left) / box.width) * WIDTH
          // 가장 가까운 점 하나를 고른다. 보간하면 없는 값을 읽어 주게 된다.
          let best = 0
          let bestDistance = Infinity
          points.forEach((p, index) => {
            const distance = Math.abs(scale.toX(p[0]) - svgX)
            if (distance < bestDistance) {
              bestDistance = distance
              best = index
            }
          })
          setHover(best)
        }}
      >
        {ticks(scale.yMin, scale.yMax).map((value) => (
          <g key={`y${value}`}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={scale.toY(value)}
              y2={scale.toY(value)}
              className="stroke-border"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 8}
              y={scale.toY(value)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {format(value)}
            </text>
          </g>
        ))}

        {ticks(scale.xMin, scale.xMax).map((value) => (
          <g key={`x${value}`}>
            <line
              x1={scale.toX(value)}
              x2={scale.toX(value)}
              y1={PAD.top}
              y2={height - PAD.bottom}
              className="stroke-border"
              strokeWidth={1}
            />
            <text
              x={scale.toX(value)}
              y={height - PAD.bottom + 16}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {format(value)}
            </text>
          </g>
        ))}

        <path d={path} fill="none" className="stroke-primary" strokeWidth={1.75} />

        {active && (
          <g>
            <line
              x1={scale.toX(active[0])}
              x2={scale.toX(active[0])}
              y1={PAD.top}
              y2={height - PAD.bottom}
              className="stroke-primary/40"
              strokeDasharray="3 3"
            />
            <circle
              cx={scale.toX(active[0])}
              cy={scale.toY(active[1])}
              r={4}
              className="fill-primary"
            />
            <text
              x={Math.min(scale.toX(active[0]) + 8, WIDTH - PAD.right - 130)}
              y={Math.max(scale.toY(active[1]) - 10, PAD.top + 12)}
              className="fill-foreground text-[11px] font-medium"
            >
              {format(active[0])} , {format(active[1])}
            </text>
          </g>
        )}

        <text
          x={PAD.left + scale.plotWidth / 2}
          y={height - 6}
          textAnchor="middle"
          className="fill-muted-foreground text-[12px]"
        >
          {xLabel}
        </text>
        <text
          x={14}
          y={PAD.top + scale.plotHeight / 2}
          textAnchor="middle"
          transform={`rotate(-90 14 ${PAD.top + scale.plotHeight / 2})`}
          className="fill-muted-foreground text-[12px]"
        >
          {yLabel}
        </text>
      </svg>
    </div>
  )
}
