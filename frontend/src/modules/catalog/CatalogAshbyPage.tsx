/**
 * Ashby 차트 — **물성 대 물성의 재료 지도.**
 *
 * 두 축의 수치 대표값을 다 가진 재료만 점이 된다. 물성은 자릿수가 갈리는 것이
 * 많아 로그축이 기본이고, 0·음수 점은 로그축에서 빠지되 **몇 점이 빠졌는지
 * 말한다** — 조용히 사라진 점은 없는 재료처럼 보인다.
 *
 * 차트는 SVG 직접 그리기다 — 산점도 하나에 차트 라이브러리를 들이지 않는다
 * (이 저장소의 차트들이 도메인 모듈 소유라 공통에 올릴 수도 없다).
 */

import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { CATEGORY_LABELS, DOMAIN_LABELS, catalogApi } from '@/modules/catalog/api'
import type { AshbyResult } from '@/modules/catalog/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { useResource } from '@/shared/hooks/useResource'

const WIDTH = 860
const HEIGHT = 520
const PAD = { left: 64, right: 16, top: 12, bottom: 44 }

//: 그룹 색 — 색약 안전(Okabe–Ito) 팔레트.
const PALETTE = [
  '#0072B2',
  '#E69F00',
  '#009E73',
  '#CC79A7',
  '#56B4E9',
  '#D55E00',
  '#F0E442',
  '#999999',
]

function ticksOf(min: number, max: number, log: boolean): number[] {
  if (log) {
    const lo = Math.floor(Math.log10(min))
    const hi = Math.ceil(Math.log10(max))
    return Array.from({ length: hi - lo + 1 }, (_, at) => 10 ** (lo + at))
  }
  const span = max - min || 1
  const step = 10 ** Math.floor(Math.log10(span / 4))
  const nice = [step, step * 2, step * 5, step * 10].find((one) => span / one <= 6) ?? step
  const start = Math.ceil(min / nice) * nice
  const out: number[] = []
  for (let tick = start; tick <= max; tick += nice) out.push(tick)
  return out
}

function fmtTick(value: number): string {
  const magnitude = Math.abs(value)
  if (magnitude !== 0 && (magnitude >= 1e4 || magnitude < 1e-2)) return value.toExponential(0)
  return String(Number(value.toPrecision(3)))
}

function Scatter({
  data,
  logX,
  logY,
  onPick,
}: {
  data: AshbyResult
  logX: boolean
  logY: boolean
  onPick: (id: string) => void
}) {
  const visible = data.points.filter(
    (point) => (!logX || point.x > 0) && (!logY || point.y > 0)
  )
  const dropped = data.points.length - visible.length
  if (visible.length === 0) {
    return <p className="text-muted-foreground py-10 text-center text-sm">그릴 점이 없습니다.</p>
  }
  const sx = visible.map((point) => (logX ? Math.log10(point.x) : point.x))
  const sy = visible.map((point) => (logY ? Math.log10(point.y) : point.y))
  const [minX, maxX] = [Math.min(...sx), Math.max(...sx)]
  const [minY, maxY] = [Math.min(...sy), Math.max(...sy)]
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  const plotW = WIDTH - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const toX = (value: number) =>
    PAD.left + (((logX ? Math.log10(value) : value) - minX) / spanX) * plotW
  const toY = (value: number) =>
    PAD.top + plotH - (((logY ? Math.log10(value) : value) - minY) / spanY) * plotH

  const groups = [...new Set(visible.map((point) => point.group))].sort()
  const colorOf = new Map(groups.map((group, at) => [group, PALETTE[at % PALETTE.length]]))
  const xTicks = ticksOf(
    logX ? 10 ** minX : minX,
    logX ? 10 ** maxX : maxX,
    logX
  ).filter((tick) => toX(tick) >= PAD.left - 1 && toX(tick) <= WIDTH - PAD.right + 1)
  const yTicks = ticksOf(
    logY ? 10 ** minY : minY,
    logY ? 10 ** maxY : maxY,
    logY
  ).filter((tick) => toY(tick) <= PAD.top + plotH + 1 && toY(tick) >= PAD.top - 1)

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-md border">
        <svg
          role="img"
          aria-label="Ashby 산점도"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="min-w-[640px]"
        >
          {xTicks.map((tick) => (
            <g key={`x${tick}`}>
              <line
                x1={toX(tick)}
                x2={toX(tick)}
                y1={PAD.top}
                y2={PAD.top + plotH}
                stroke="currentColor"
                strokeOpacity={0.08}
              />
              <text
                x={toX(tick)}
                y={HEIGHT - PAD.bottom + 16}
                textAnchor="middle"
                fontSize={11}
                fill="currentColor"
                opacity={0.7}
              >
                {fmtTick(tick)}
              </text>
            </g>
          ))}
          {yTicks.map((tick) => (
            <g key={`y${tick}`}>
              <line
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={toY(tick)}
                y2={toY(tick)}
                stroke="currentColor"
                strokeOpacity={0.08}
              />
              <text
                x={PAD.left - 6}
                y={toY(tick) + 4}
                textAnchor="end"
                fontSize={11}
                fill="currentColor"
                opacity={0.7}
              >
                {fmtTick(tick)}
              </text>
            </g>
          ))}
          {visible.map((point) => (
            <circle
              key={point.id}
              cx={toX(point.x)}
              cy={toY(point.y)}
              r={4}
              fill={colorOf.get(point.group)}
              fillOpacity={0.75}
              className="cursor-pointer"
              onClick={() => onPick(String(point.id))}
            >
              <title>
                {point.name} ({point.group})
              </title>
            </circle>
          ))}
        </svg>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        {groups.map((group) => (
          <span key={group} className="inline-flex items-center gap-1">
            <span
              className="inline-block size-2.5 rounded-full"
              style={{ background: colorOf.get(group) }}
            />
            {CATEGORY_LABELS[group] ?? group}
          </span>
        ))}
        <span className="text-muted-foreground ml-auto">
          {visible.length}종 표시
          {dropped > 0 && ` (로그축이라 0·음수 ${dropped}점 제외)`}
        </span>
      </div>
    </div>
  )
}

export default function CatalogAshbyPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const x = params.get('x') ?? ''
  const y = params.get('y') ?? ''
  const color = (params.get('color') === 'subsystem' ? 'subsystem' : 'category') as
    | 'category'
    | 'subsystem'
  const [logX, setLogX] = useState(true)
  const [logY, setLogY] = useState(true)

  const axes = useResource(() => catalogApi.axes(), [])
  const chart = useResource<AshbyResult | null>(
    () => (x && y ? catalogApi.ashby(x, y, color) : Promise.resolve(null)),
    [x, y, color]
  )

  function set(key: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  const byDomain = new Map<string, NonNullable<typeof axes.data>>()
  for (const axis of axes.data ?? []) {
    const list = byDomain.get(axis.domain) ?? []
    list.push(axis)
    byDomain.set(axis.domain, list)
  }

  const axisSelect = (label: string, value: string, key: string) => (
    <select
      aria-label={label}
      className="border-input bg-background h-9 max-w-72 rounded-md border px-2 text-sm"
      value={value}
      onChange={(event) => set(key, event.target.value)}
    >
      <option value="">{label} 고르기</option>
      {[...byDomain.entries()].map(([domain, list]) => (
        <optgroup key={domain} label={DOMAIN_LABELS[domain] ?? domain}>
          {list.map((axis) => (
            <option key={axis.key} value={axis.key}>
              {axis.name}
              {axis.unit && axis.unit !== '1' ? ` (${axis.unit})` : ''} · {axis.material_count}종
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )

  return (
    <div className="space-y-4">
      <PageHeader
        title="Ashby 차트"
        description="두 물성의 대표값으로 문헌 재료 전체를 지도처럼 봅니다. 두 값을 다 가진 재료만 점이 되고, 점을 누르면 그 재료로 갑니다."
      />
      <ErrorNotice error={axes.error} />
      <ErrorNotice error={chart.error} />

      <div className="flex flex-wrap items-center gap-2">
        {axisSelect('가로축', x, 'x')}
        {axisSelect('세로축', y, 'y')}
        <select
          aria-label="색 구분"
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={color}
          onChange={(event) => set('color', event.target.value)}
        >
          <option value="category">분류로 색</option>
          <option value="subsystem">계통으로 색</option>
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={logX} onChange={(e) => setLogX(e.target.checked)} />
          가로 로그
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={logY} onChange={(e) => setLogY(e.target.checked)} />
          세로 로그
        </label>
      </div>

      {!x || !y ? (
        <p className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          가로축과 세로축 물성을 고르면 지도가 섭니다 — 목록은 재료 수가 많은 물성부터입니다.
        </p>
      ) : (
        chart.data && (
          <Scatter
            data={chart.data}
            logX={logX}
            logY={logY}
            onPick={(id) => navigate(`/catalog/${id}`)}
          />
        )
      )}
    </div>
  )
}
