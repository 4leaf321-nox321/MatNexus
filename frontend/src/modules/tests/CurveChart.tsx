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
  overlay?: { points: [number, number][]; label: string }
  /**
   * 겹쳐 그릴 두 번째 선. **적합 결과는 겹쳐 보지 않으면 판단할 수 없다** —
   * RMSE 가 작아도 항복 근처만 크게 어긋나 있을 수 있고, 그것은 숫자가 아니라
   * 모양으로 보인다. 위 주석이 "Phase 3 에서 다시 판단한다" 고 한 그 지점이다.
   * 선 두 개까지는 라이브러리 없이 충분하다.
   */
  pointsLabel?: string
  /**
   * 로그 축. **마스터커브는 이것 없이 못 읽는다** — 주파수가 1e-6 에서 20 Hz
   * 까지 일곱 자릿수에 걸치고, 저장 탄성률도 3 MPa 에서 3 GPa 까지 세 자릿수다.
   * 선형으로 그리면 점 대부분이 왼쪽 끝 한 칸에 뭉친다.
   *
   * 눈금 라벨은 **원래 값**으로 적는다(1e-6 · 0.001 · 1 …). 사람은 Hz 로 읽지
   * log Hz 로 읽지 않는다.
   */
  logX?: boolean
  logY?: boolean
  /**
   * x 축의 한 지점에 세로선을 긋는다. **외삽을 그릴 때 없으면 안 된다** — 늘린
   * 구간과 측정 구간은 선이 이어져 있어서, 경계를 표시하지 않으면 어디까지가
   * 시험이고 어디부터가 식의 주장인지 구별할 방법이 없다.
   */
  marker?: { x: number; label: string }
  /**
   * 뒤에 **흐리게** 깔 선들. 대표 곡선을 만든 원곡선들이 여기 온다.
   *
   * **평균만 보여 주면 그것이 적절한지 알 방법이 없다.** 셋이 겹쳐 있는데
   * 하나가 딴 데로 가서 평균이 끌려간 것인지, 애초에 흩어짐이 그만큼인지 —
   * 평균선 하나로는 두 경우가 똑같이 생겼다.
   *
   * 축 범위에 함께 넣는다. 안 넣으면 판 밖으로 나간 곡선이 잘려 보이고,
   * **잘린 그림은 흩어짐을 실제보다 작아 보이게 한다.**
   */
  background?: { points: [number, number][]; label: string }[]
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

export function CurveChart({
  points,
  xLabel,
  yLabel,
  height = 380,
  overlay,
  background,
  pointsLabel,
  logX = false,
  logY = false,
  marker,
}: CurveChartProps) {
  const [hover, setHover] = useState<number | null>(null)

  const scale = useMemo(() => {
    if (points.length === 0) return null
    // 겹쳐 그리는 선도 축 범위에 넣는다. 안 넣으면 적합 곡선이 판을 벗어나
    // 잘려 보이고, 잘린 그림으로는 잘 맞는지 알 수 없다.
    const all = [
      ...points,
      ...(overlay?.points ?? []),
      ...(background ?? []).flatMap((one) => one.points),
    ]
    // 로그 축이면 **자리 계산만** log10 으로 한다. 원래 값은 그대로 두고 눈금
    // 라벨에서 되돌린다 — 툴팁이 log 값을 보여 주면 아무도 못 읽는다.
    const tx = (value: number) => (logX ? Math.log10(Math.max(value, Number.MIN_VALUE)) : value)
    const ty = (value: number) => (logY ? Math.log10(Math.max(value, Number.MIN_VALUE)) : value)
    const xs = all.map((p) => tx(p[0]))
    const ys = all.map((p) => ty(p[1]))
    const xMin = Math.min(...xs)
    const xMax = Math.max(...xs)
    // 하중·응력은 0 부터 보는 것이 실무 감각이다. **로그 축에서는 안 그런다** —
    // 0 은 로그 축에 없고, 넣으면 세 자릿수짜리 곡선이 한 줄로 뭉친다.
    const yMin = logY ? Math.min(...ys) : Math.min(0, ...ys)
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
      toX: (value: number) => PAD.left + ((tx(value) - xMin) / xSpan) * plotWidth,
      toY: (value: number) => PAD.top + plotHeight - ((ty(value) - yMin) / ySpan) * plotHeight,
      // 눈금은 변환된 축에서 고르고, 자리와 라벨은 되돌려 쓴다.
      fromX: (value: number) => (logX ? 10 ** value : value),
      fromY: (value: number) => (logY ? 10 ** value : value),
      plotWidth,
      plotHeight,
    }
  }, [points, overlay, background, height, logX, logY])

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

  // 눈금은 **변환된 축**에서 고르고(로그 축이면 자릿수 간격이 된다), 자리와
  // 라벨은 원래 값으로 되돌려 쓴다.
  const yTicks = ticks(scale.yMin, scale.yMax).map((tick) => scale.fromY(tick))
  const xTicks = ticks(scale.xMin, scale.xMax).map((tick) => scale.fromX(tick))

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
        {yTicks.map((value) => (
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

        {xTicks.map((value) => (
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

        {marker !== undefined && (
          <g>
            <line
              x1={scale.toX(marker.x)}
              x2={scale.toX(marker.x)}
              y1={PAD.top}
              y2={height - PAD.bottom}
              className="stroke-amber-500"
              strokeWidth={1.5}
              strokeDasharray="5 3"
            />
            <text
              x={scale.toX(marker.x) + 4}
              y={PAD.top + 11}
              className="fill-amber-600 text-[11px]"
            >
              {marker.label}
            </text>
          </g>
        )}

        {/* **대표선보다 먼저 그린다.** SVG 는 나중에 그린 것이 위에 온다 —
            뒤에 두면 원곡선들이 대표를 덮는다. */}
        {(background ?? []).map((one) => (
          <path
            key={one.label}
            d={one.points
              .map((p, i) => `${i === 0 ? 'M' : 'L'}${scale.toX(p[0])},${scale.toY(p[1])}`)
              .join(' ')}
            fill="none"
            // **흐리되 보여야 한다.** 30% 회색 1px 로 뒀더니 대표선 아래에서
            // 사실상 안 보였고, 그러면 이 선을 그리는 뜻이 없다.
            className="stroke-sky-600 dark:stroke-sky-400"
            strokeWidth={1.1}
            opacity={0.45}
          >
            <title>{one.label}</title>
          </path>
        ))}

        <path d={path} fill="none" className="stroke-primary" strokeWidth={1.75} />

        {overlay && overlay.points.length > 0 && (
          <path
            d={overlay.points
              .map(
                (p, i) => `${i === 0 ? 'M' : 'L'}${scale.toX(p[0])},${scale.toY(p[1])}`
              )
              .join(' ')}
            fill="none"
            className="stroke-amber-600 dark:stroke-amber-500"
            strokeWidth={1.75}
            strokeDasharray="5 3"
          />
        )}

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

      {overlay && (
        <div className="flex items-center justify-center gap-4 pb-1 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="bg-primary inline-block h-0.5 w-5" />
            {pointsLabel ?? '데이터'}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5 border-t-2 border-dashed border-amber-600 dark:border-amber-500" />
            {overlay.label}
          </span>
        </div>
      )}
    </div>
  )
}
