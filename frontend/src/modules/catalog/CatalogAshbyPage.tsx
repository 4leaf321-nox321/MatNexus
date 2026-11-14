/**
 * Ashby 차트 — **물성 대 물성의 재료 지도.**
 *
 * 두 축의 수치 대표값을 다 가진 재료만 점이 된다. 물성은 자릿수가 갈리는 것이
 * 많아 로그축이 기본이고, 0·음수 점은 로그축에서 빠지되 **몇 점이 빠졌는지
 * 말한다** — 조용히 사라진 점은 없는 재료처럼 보인다.
 *
 * **값이 똑같은 재료는 한 점으로 묶고, 누른 자리 근처의 재료를 모두 고르게 한다**(2026-11-15).
 * 재료 470~830종이 한 판에 찍혀 셋에 하나는 다른 점에 완전히 덮였고, 그 대부분은 값이 같아
 * 한 자리에 포개진 것이라 확대로도 안 풀렸다. 추정값(문헌 4등급)은 빈 점이다.
 *
 * 차트는 SVG 직접 그리기다 — 산점도 하나에 차트 라이브러리를 들이지 않는다
 * (이 저장소의 차트들이 도메인 모듈 소유라 공통에 올릴 수도 없다).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { CATEGORY_LABELS, DOMAIN_LABELS, catalogApi, systemUnit, unitLabelAs } from '@/modules/catalog/api'
import type { AshbyResult } from '@/modules/catalog/api'
import { panBy, toViewBox, zoomAt } from '@/modules/catalog/ashbyView'
import type { Box } from '@/modules/catalog/ashbyView'
import { UnitModeToggle, useUnitMode } from '@/modules/catalog/unitMode'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { useResource } from '@/shared/hooks/useResource'
import { display } from '@/shared/units'

const WIDTH = 860
const HEIGHT = 480
//: 왼쪽·아래 여백에 축 라벨(물성 이름 + 단위)이 들어간다.
const PAD = { left: 88, right: 16, top: 12, bottom: 64 }

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

/** 한 자리에 포개진 점들 — 값이 똑같아 아무리 당겨도 안 떨어진다. */
interface Stack {
  key: string
  px: number
  py: number
  members: AshbyResult['points']
}

/** 누른 점에서 이 거리(viewBox) 안의 재료를 함께 고르게 한다 — 점 지름이다. */
const PICK_RADIUS = 8
/** 추정값(문헌 등급 4) — 빈 점으로 그린다. */
const ESTIMATED_TIER = 4
/** 한 번 굴릴 때 얼마나. */
const WHEEL_STEP = 0.85
/** 이보다 덜 움직였으면 끈 것이 아니라 누른 것이다(화면 px). */
const DRAG_MIN = 4

function Scatter({
  data,
  logX,
  logY,
  xLabel,
  yLabel,
  onPick,
}: {
  data: AshbyResult
  logX: boolean
  logY: boolean
  xLabel: string
  yLabel: string
  onPick: (id: string) => void
}) {
  const frame = useRef<SVGSVGElement | null>(null)
  /** 보는 범위(축에 그리는 값). `null` 이면 전체다. */
  const [view, setView] = useState<Box | null>(null)
  /** 누른 자리 근처의 재료들 — 둘 이상이면 목록에서 고른다. */
  const [choices, setChoices] = useState<AshbyResult['points'] | null>(null)
  const drag = useRef<{ x: number; y: number; box: Box; moved: boolean } | null>(null)
  /** 끌고 난 직후의 click 은 고르기가 아니다. */
  const dragged = useRef(false)

  const visible = useMemo(
    () => data.points.filter((point) => (!logX || point.x > 0) && (!logY || point.y > 0)),
    [data, logX, logY]
  )
  const dropped = data.points.length - visible.length
  const scaleX = (value: number) => (logX ? Math.log10(value) : value)
  const scaleY = (value: number) => (logY ? Math.log10(value) : value)

  const full = useMemo<Box | null>(() => {
    if (visible.length === 0) return null
    const sx = visible.map((point) => (logX ? Math.log10(point.x) : point.x))
    const sy = visible.map((point) => (logY ? Math.log10(point.y) : point.y))
    const [x0, x1] = [Math.min(...sx), Math.max(...sx)]
    const [y0, y1] = [Math.min(...sy), Math.max(...sy)]
    // 점이 하나거나 한 줄이면 폭이 0 이다 — 1 을 준다(전과 같다).
    return { x0, x1: x1 > x0 ? x1 : x0 + 1, y0, y1: y1 > y0 ? y1 : y0 + 1 }
  }, [visible, logX, logY])

  // 축 · 자료가 바뀌면 옛 범위는 다른 값의 것이다 — 전체로 돌아간다. 값으로 견준다(부모가 다시
  // 그릴 때마다 점 배열이 새로 지어져, 객체로 견주면 그때마다 확대가 풀린다).
  const fullKey = full ? `${full.x0}|${full.x1}|${full.y0}|${full.y1}|${visible.length}` : ''
  useEffect(() => {
    setView(null)
    setChoices(null)
  }, [fullKey])

  const plotW = WIDTH - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const box = view ?? full
  const fullRef = useRef(full)
  fullRef.current = full
  const boxRef = useRef(box)
  boxRef.current = box

  // **네이티브로 붙인다** — React 의 onWheel 은 passive 라 preventDefault 가 안 먹어, 확대할 때
  // 페이지가 함께 굴러간다(곡선 차트와 같은 까닭).
  const drawn = full !== null
  useEffect(() => {
    const node = frame.current
    if (!node) return
    function wheel(event: WheelEvent) {
      const whole = fullRef.current
      const current = boxRef.current
      if (!node || !whole || !current || event.deltaY === 0) return
      const at = toViewBox(event.clientX, event.clientY, node.getBoundingClientRect(), WIDTH, HEIGHT)
      if (!at) return
      event.preventDefault()
      // 판(plot) 안에서의 비율 — 여백을 뺀다. 세로는 아래가 0 이다.
      const shareX = Math.min(Math.max((at[0] - PAD.left) / plotW, 0), 1)
      const shareY = Math.min(Math.max(1 - (at[1] - PAD.top) / plotH, 0), 1)
      setView(zoomAt(current, whole, shareX, shareY, event.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP))
      setChoices(null)
    }
    node.addEventListener('wheel', wheel, { passive: false })
    return () => node.removeEventListener('wheel', wheel)
  }, [drawn, plotW, plotH])

  if (!full || !box) {
    return <p className="text-muted-foreground py-10 text-center text-sm">그릴 점이 없습니다.</p>
  }
  const toX = (value: number) => PAD.left + ((scaleX(value) - box.x0) / (box.x1 - box.x0)) * plotW
  const toY = (value: number) =>
    PAD.top + plotH - ((scaleY(value) - box.y0) / (box.y1 - box.y0)) * plotH

  const groups = [...new Set(visible.map((point) => point.group))].sort()
  const colorOf = new Map(groups.map((group, at) => [group, PALETTE[at % PALETTE.length]]))
  const xTicks = ticksOf(logX ? 10 ** box.x0 : box.x0, logX ? 10 ** box.x1 : box.x1, logX).filter(
    (tick) => toX(tick) >= PAD.left - 1 && toX(tick) <= WIDTH - PAD.right + 1
  )
  const yTicks = ticksOf(logY ? 10 ** box.y0 : box.y0, logY ? 10 ** box.y1 : box.y1, logY).filter(
    (tick) => toY(tick) <= PAD.top + plotH + 1 && toY(tick) >= PAD.top - 1
  )

  // **값이 똑같은 재료는 한 점으로 묶는다**(2026-11-15). 한 자리에 51종이 포개진 곳이 있었고,
  // 맨 위 하나만 눌려 나머지는 지도에서 갈 길이 없었다 — 당겨도 안 떨어진다. 잰 값이 위에 온다.
  const stacks = new Map<string, Stack>()
  for (const point of visible) {
    const key = `${point.x}|${point.y}`
    const found = stacks.get(key)
    if (found) found.members.push(point)
    else stacks.set(key, { key, px: toX(point.x), py: toY(point.y), members: [point] })
  }
  const drawnStacks = [...stacks.values()]
    .map((stack) => ({
      ...stack,
      members: [...stack.members].sort((left, right) => left.tier - right.tier),
    }))
    // 판 밖(확대해서 벗어난 것)은 안 그린다.
    .filter(
      (stack) =>
        stack.px >= PAD.left - 4 &&
        stack.px <= WIDTH - PAD.right + 4 &&
        stack.py >= PAD.top - 4 &&
        stack.py <= PAD.top + plotH + 4
    )
  const crowded = [...stacks.values()].filter((stack) => stack.members.length > 1)
  const hidden = crowded.reduce((sum, stack) => sum + stack.members.length, 0)
  const estimated = visible.filter((point) => point.tier >= ESTIMATED_TIER).length

  function pick(stack: Stack) {
    if (dragged.current) return
    // **누른 점 근처를 모두** — 일부만 겹친 점도 맨 위 것만 눌렸다.
    const near = drawnStacks
      .filter((one) => Math.hypot(one.px - stack.px, one.py - stack.py) <= PICK_RADIUS)
      .flatMap((one) => one.members)
    if (near.length === 1) onPick(String(near[0].id))
    else setChoices(near)
  }

  return (
    <div className="space-y-2">
      <div className="rounded-md border">
        {/* **한 화면에 들어온다.** 뷰포트 높이에 맞춰 줄어들고(viewBox 비율 유지),
            머리글·조작줄·범례 몫을 뺀 만큼만 차지한다 — 지도는 스크롤 없이 한눈이다. */}
        <svg
          ref={frame}
          role="img"
          aria-label="Ashby 산점도"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className={`h-[max(320px,calc(100vh-380px))] w-full ${view ? 'cursor-grab' : ''}`}
          onDoubleClick={() => setView(null)}
          onMouseDown={(event) => {
            dragged.current = false
            if (view) drag.current = { x: event.clientX, y: event.clientY, box: view, moved: false }
          }}
          onMouseMove={(event) => {
            const held = drag.current
            if (!held) return
            const rect = event.currentTarget.getBoundingClientRect()
            const scale = Math.min(rect.width / WIDTH, rect.height / HEIGHT)
            if (!(scale > 0)) return
            const dx = event.clientX - held.x
            const dy = event.clientY - held.y
            if (!held.moved && Math.hypot(dx, dy) < DRAG_MIN) return
            held.moved = true
            dragged.current = true
            // 판의 폭 · 높이로 나눈다 — 손이 데이터를 잡은 것처럼. 세로는 화면이 아래로 자란다.
            setView(panBy(held.box, full, dx / scale / plotW, -dy / scale / plotH) ?? held.box)
          }}
          onMouseUp={() => {
            drag.current = null
          }}
          onMouseLeave={() => {
            drag.current = null
          }}
        >
          <defs>
            <clipPath id="ashby-plot">
              <rect x={PAD.left - 5} y={PAD.top - 5} width={plotW + 10} height={plotH + 10} />
            </clipPath>
          </defs>
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
          {/* 축 라벨 — 단위가 없는 지도는 숫자가 아니라 그림이다. */}
          <text
            x={PAD.left + plotW / 2}
            y={HEIGHT - 8}
            textAnchor="middle"
            fontSize={13}
            fontWeight={600}
            fill="currentColor"
          >
            {xLabel}
          </text>
          <text
            x={14}
            y={PAD.top + plotH / 2}
            textAnchor="middle"
            fontSize={13}
            fontWeight={600}
            fill="currentColor"
            transform={`rotate(-90 14 ${PAD.top + plotH / 2})`}
          >
            {yLabel}
          </text>
          <g clipPath="url(#ashby-plot)">
            {drawnStacks.map((stack) => {
              const top = stack.members[0]
              const color = colorOf.get(top.group)
              const hollow = top.tier >= ESTIMATED_TIER
              return (
                <g key={stack.key} className="cursor-pointer" onClick={() => pick(stack)}>
                  {/* 여럿이 포개진 자리는 테를 두른다 — 「여기 더 있다」. */}
                  {stack.members.length > 1 && (
                    <circle
                      cx={stack.px}
                      cy={stack.py}
                      r={6.5}
                      fill="none"
                      stroke="currentColor"
                      strokeOpacity={0.55}
                    />
                  )}
                  <circle
                    cx={stack.px}
                    cy={stack.py}
                    r={4}
                    fill={hollow ? 'transparent' : color}
                    fillOpacity={hollow ? 1 : 0.75}
                    stroke={hollow ? color : 'none'}
                    strokeWidth={hollow ? 1.5 : 0}
                    data-estimated={hollow ? 'true' : undefined}
                  >
                    <title>
                      {stack.members.length > 1
                        ? `같은 자리 ${stack.members.length}종 — ${top.name} 외`
                        : `${top.name} (${top.group})${hollow ? ' · 추정값' : ''}`}
                    </title>
                  </circle>
                </g>
              )
            })}
          </g>
        </svg>
      </div>
      {choices && (
        <section aria-label="겹친 재료" className="rounded-md border p-2 text-sm">
          <div className="mb-1 flex items-center gap-2">
            <b>이 자리 근처 {choices.length}종</b>
            <span className="text-muted-foreground text-xs">— 갈 재료를 고르세요.</span>
            <button
              type="button"
              className="text-muted-foreground ml-auto text-xs underline"
              onClick={() => setChoices(null)}
            >
              닫기
            </button>
          </div>
          <ul className="max-h-48 space-y-0.5 overflow-auto">
            {choices.map((point) => (
              <li key={String(point.id)}>
                <button
                  type="button"
                  className="hover:bg-muted flex w-full items-center gap-2 rounded px-1 text-left"
                  onClick={() => onPick(String(point.id))}
                >
                  <span
                    className="inline-block size-2.5 shrink-0 rounded-full"
                    style={{ background: colorOf.get(point.group) }}
                  />
                  <span>{point.name}</span>
                  <span className="text-muted-foreground text-xs">
                    {CATEGORY_LABELS[point.group] ?? point.group}
                    {point.tier >= ESTIMATED_TIER && ' · 추정값'}
                  </span>
                  <span className="ml-auto font-mono text-xs tabular-nums">
                    {fmtTick(point.x)} · {fmtTick(point.y)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
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
        {estimated > 0 && (
          <span className="inline-flex items-center gap-1">
            <span className="inline-block size-2.5 rounded-full border border-current" />
            빈 점 = 추정값(문헌 4등급) {estimated}종
          </span>
        )}
        {view && (
          <button type="button" className="underline" onClick={() => setView(null)}>
            전체 보기
          </button>
        )}
        <span className="text-muted-foreground ml-auto">
          {visible.length}종 표시
          {dropped > 0 && ` (로그축이라 0·음수 ${dropped}점 제외)`}
          {crowded.length > 0 && ` · 같은 자리 ${crowded.length}곳에 ${hidden}종(테 두른 점)`}
        </span>
      </div>
      <p className="text-muted-foreground text-xs">
        휠로 확대, 확대한 뒤 끌어서 이동, 더블클릭으로 전체. 점을 누르면 그 재료로 가고, 근처에
        여럿이면 목록에서 고릅니다.
      </p>
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
  const [units, setUnits] = useUnitMode()

  const axes = useResource(() => catalogApi.axes(), [])
  const chart = useResource<AshbyResult | null>(
    () => (x && y ? catalogApi.ashby(x, y, color) : Promise.resolve(null)),
    [x, y, color]
  )

  // 표시용 모드면 점·눈금을 공용 표로 환산해 그린다 — 축 라벨과 숫자가 같은
  // 단위여야 한다. 오프셋 단위(°C)는 로그가 무의미하므로 그 축만 선형으로.
  const xShow = units === 'display' ? display(systemUnit(chart.data?.x_unit ?? '')) : null
  const yShow = units === 'display' ? display(systemUnit(chart.data?.y_unit ?? '')) : null
  const shown: AshbyResult | null = chart.data
    ? {
        ...chart.data,
        points: chart.data.points.map((point) => ({
          ...point,
          x: xShow ? point.x * xShow.factor + xShow.offset : point.x,
          y: yShow ? point.y * yShow.factor + yShow.offset : point.y,
        })),
      }
    : null
  const xHasOffset = (xShow?.offset ?? 0) !== 0
  const yHasOffset = (yShow?.offset ?? 0) !== 0

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

  /** 축 라벨 — 「물성 이름 (단위)」, 단위는 고른 모드로. 무차원(`1`)은 생략. */
  function axisLabel(key: string, unit: string | null | undefined): string {
    const name = (axes.data ?? []).find((axis) => axis.key === key)?.name ?? key
    const label = unitLabelAs(units, unit)
    return label ? `${name} (${label})` : name
  }

  const axisSelect = (label: string, value: string, key: string) => (
    <select
      aria-label={label}
      className="border-input bg-background h-9 max-w-72 rounded-md border px-2 text-sm"
      value={value}
      onChange={(event) => set(key, event.target.value)}
    >
      <option value="">{label} 선택</option>
      {[...byDomain.entries()].map(([domain, list]) => (
        <optgroup key={domain} label={DOMAIN_LABELS[domain] ?? domain}>
          {list.map((axis) => (
            <option key={axis.key} value={axis.key}>
              {axis.name}
              {axis.unit && axis.unit !== '1' ? ` (${systemUnit(axis.unit)})` : ''} ·{' '}
              {axis.material_count}종
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
        description="두 물성의 대표값으로 문헌 재료 전체를 지도처럼 봅니다. 두 값을 다 가진 재료만 점이 되고, 점을 누르면 그 재료로 갑니다(근처에 여럿이면 목록에서 고릅니다)."
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
        <label
          className="flex items-center gap-1 text-sm"
          title={xHasOffset ? '°C 처럼 원점이 다른 단위는 로그축이 무의미합니다' : undefined}
        >
          <input
            type="checkbox"
            checked={logX && !xHasOffset}
            disabled={xHasOffset}
            onChange={(e) => setLogX(e.target.checked)}
          />
          가로 로그
        </label>
        <label
          className="flex items-center gap-1 text-sm"
          title={yHasOffset ? '°C 처럼 원점이 다른 단위는 로그축이 무의미합니다' : undefined}
        >
          <input
            type="checkbox"
            checked={logY && !yHasOffset}
            disabled={yHasOffset}
            onChange={(e) => setLogY(e.target.checked)}
          />
          세로 로그
        </label>
        <UnitModeToggle mode={units} onChange={setUnits} />
      </div>

      {!x || !y ? (
        <p className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          가로축과 세로축 물성을 고르면 지도가 섭니다 — 목록은 재료 수가 많은 물성부터입니다.
        </p>
      ) : (
        shown && (
          <Scatter
            data={shown}
            logX={logX && !xHasOffset}
            logY={logY && !yHasOffset}
            xLabel={axisLabel(x, shown.x_unit)}
            yLabel={axisLabel(y, shown.y_unit)}
            onPick={(id) => navigate(`/catalog/${id}`)}
          />
        )
      )}
    </div>
  )
}
