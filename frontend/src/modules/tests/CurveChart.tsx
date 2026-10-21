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
 * **Phase 3 에서 다시 판단했다(2026-08-26).** 다중 곡선·확대·로그축이 실제로
 * 필요해졌고, 그래도 직접 그리기로 했다.
 *
 *   - 곡선이 11개(대표 + 시편 10)로 늘었지만 점은 여전히 300~1200 이다. 라이브
 *     러리가 값을 하는 지점(수만 점, 실시간 갱신)에 아직 안 닿았다.
 *   - 필요한 상호작용이 **휠 확대·끌어 옮기기·전체 보기·여러 계열 값 읽기** 넷
 *     인데, 넷 다 여기서 스무 줄 안쪽이다. 라이브러리를 넣으면 번들이 곱절
 *     가까이 늘고(§8.5 번들 예산) 폐쇄망 배포에 의존성이 하나 더 붙는다.
 *   - 테마·단위·접근성이 이미 이 파일의 규칙을 따른다. 갈아 끼우면 그 셋을
 *     다시 맞춰야 한다.
 *
 * 점이 수만으로 늘거나 실시간 갱신이 필요해지면 그때는 uPlot 쪽이 값을 한다.
 *
 * **영역 확대를 더했다(2026-10-20).** 사용자 보고: 탄성 구간보다 소성 구간이 긴 재료는 앞
 * 구간의 기울기를 볼 수 없다 — 「확대 · 화면 이동이 필요하다」. 둘 다 있었지만 두 가지가 막고
 * 있었다. ① 시험 상세처럼 **점이 나중에 오는 자리에서는 휠이 아예 안 붙었다**(판이 없을 때 한
 * 번만 붙였다) — 그러면 확대가 안 되고, 끌기는 확대된 뒤에만 켜지므로 이동도 안 된다. ② 휠은
 * 가로 · 세로를 같이 당긴다 — 변형률 0.3 % 의 탄성 구간을 펴려고 가로를 백 배 당기면 세로도
 * 백 배 당겨져 응력 몇 MPa 만 남는다. 그래서 **끌어서 사각형으로 고르고, 옆으로만 끌면 가로만**
 * 편다. 이동은 「끌기」 를 「이동」 으로 바꿔서, Shift+휠은 가로만 당긴다.
 *
 * 점은 **표시 단위로 이미 환산된 것**을 받는다. 이 컴포넌트는 단위를 모른다 —
 * 알면 SI 변환 규칙이 화면에도 생겨 두 곳이 된다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import { AxisScaleToggle } from '@/shared/components/AxisScaleToggle'

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
   *
   * **처음 보일 축일 뿐이다(2026-09-29).** 차트 위의 「가로축 · 세로축 선형/로그」 단추로
   * 사람이 바꾼다 — 모든 곡선에서. 로그 축에서는 0 이하 점을 그리지 않고 몇 점을 뺐는지
   * 적는다(변형률처럼 0 에서 시작하는 곡선에서 한 점 때문에 축이 수백 자릿수로 무너졌다).
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
  background?: { points: [number, number][]; label: string; tone?: string; dashed?: boolean }[]
  /**
   * `tone` 은 그 선의 색(Tailwind `stroke-*` 클래스). **안 주면 전부 같은
   * 파랑**이고, 그것이 시편 원곡선에는 맞다 — 서로 구별할 것이 아니라 흩어짐을
   * 보는 것이라서다.
   *
   * 처리 단계를 겹칠 때는 다르다. 「자르기 전」 과 「자른 뒤」 가 같은 색이면
   * 어느 쪽이 어느 쪽인지 그림에서 알 수 없고, 그러면 겹쳐 놓은 뜻이 없다.
   *
   * `dashed` 는 **참고선**이다 — 하한 곡선 곁의 평균처럼, 원곡선들과 섞여 보이면 안 되는 선.
   */
}

/** 보고 있는 범위. 변환된 축(로그면 log10)의 값이다. */
interface Box {
  xMin: number
  xMax: number
  yMin: number
  yMax: number
}

/** 한 번 굴릴 때 얼마나. 1 보다 작으면 당겨 보는 쪽이다. */
const WHEEL_STEP = 0.85
/** 전체 범위의 몇 분의 일까지 좁힐 수 있나. 더 파고들면 점이 안 남는다. */
const MAX_ZOOM = 500
/** 이보다 짧게 끈 가로(판 좌표)는 그냥 누른 것이다. */
const PICK_MIN = 6
/**
 * 세로로 이만큼(판 높이의 비율) 못 끌었으면 **가로만** 편다. 옆으로 끌 때 손은 늘 조금
 * 위아래로 흔들린다 — 그 흔들림을 세로 확대로 읽으면 곡선이 얇은 띠 밖으로 사라진다.
 */
const FLAT_SHARE = 0.08

const PAD = { top: 16, right: 20, bottom: 44, left: 68 }
const WIDTH = 760

/** 화면 비율을 **판(plot) 안의 비율**로. 축 여백만큼 어긋나는 것을 걷는다. */
function plotShare(share: number, axis: 'x' | 'y'): number {
  const before = axis === 'x' ? PAD.left : PAD.top
  const after = axis === 'x' ? PAD.right : PAD.bottom
  const total = axis === 'x' ? WIDTH : 1
  // y 는 높이를 모르므로 비율만 쓴다 — 여백 비중이 작아 실사용에서 티가 안 난다.
  if (axis === 'y') return Math.min(Math.max(share, 0), 1)
  const inside = (share * total - before) / (total - before - after)
  return Math.min(Math.max(inside, 0), 1)
}

/**
 * 확대 범위를 **전체 밖으로 못 나가게** 하고, 너무 파고들지도 못하게 한다.
 *
 * 안 막으면 한 번 잘못 굴렸을 때 곡선이 사라지고, 사람은 데이터가 없어진 줄
 * 안다 — 「전체 보기」 가 있어도 그 순간에는 고장으로 읽힌다.
 */
function clamp(box: Box, whole: Box | null): Box {
  if (!whole) return box
  const minX = (whole.xMax - whole.xMin) / MAX_ZOOM
  const minY = (whole.yMax - whole.yMin) / MAX_ZOOM
  let { xMin, xMax, yMin, yMax } = box
  if (xMax - xMin < minX) {
    const mid = (xMin + xMax) / 2
    xMin = mid - minX / 2
    xMax = mid + minX / 2
  }
  if (yMax - yMin < minY) {
    const mid = (yMin + yMax) / 2
    yMin = mid - minY / 2
    yMax = mid + minY / 2
  }
  // 전체보다 넓어지면 전체로 돌린다.
  if (xMax - xMin >= whole.xMax - whole.xMin && yMax - yMin >= whole.yMax - whole.yMin) {
    return { ...whole }
  }
  return { xMin, xMax, yMin, yMax }
}

/** 끌어 그린 사각형 — 판(viewBox) 좌표. */
interface Pick {
  x0: number
  y0: number
  x1: number
  y1: number
}

/**
 * 끌어 그린 사각형을 **판 안에서 실제로 쓸 모양**으로. 세로가 얇으면 판 높이 전체로 —
 * 가로만 펴는 것이다(그릴 때도 그 모양으로 보여 줘야 놓았을 때 놀라지 않는다). 가로가
 * 짧으면 판 너비 전체로 — 세로만. 둘 다 짧으면 그냥 누른 것이라 `null`.
 */
function pickShape(
  pick: Pick,
  height: number,
): { left: number; right: number; top: number; bottom: number; wide: boolean; tall: boolean } | null {
  const plotHeight = height - PAD.top - PAD.bottom
  const inX = (value: number) => Math.min(Math.max(value, PAD.left), WIDTH - PAD.right)
  const inY = (value: number) => Math.min(Math.max(value, PAD.top), height - PAD.bottom)
  const left = inX(Math.min(pick.x0, pick.x1))
  const right = inX(Math.max(pick.x0, pick.x1))
  const top = inY(Math.min(pick.y0, pick.y1))
  const bottom = inY(Math.max(pick.y0, pick.y1))
  const wide = right - left >= PICK_MIN
  const tall = bottom - top >= Math.max(PICK_MIN, plotHeight * FLAT_SHARE)
  if (!wide && !tall) return null
  return {
    left: wide ? left : PAD.left,
    right: wide ? right : WIDTH - PAD.right,
    top: tall ? top : PAD.top,
    bottom: tall ? bottom : height - PAD.bottom,
    wide,
    tall,
  }
}

/** 고른 사각형을 **보고 있는 범위**(변환된 축)로. 짧게 끈 축은 그대로 둔다. */
function pickBox(pick: Pick, box: Box, height: number): Box | null {
  const shape = pickShape(pick, height)
  if (!shape) return null
  const plotWidth = WIDTH - PAD.left - PAD.right
  const plotHeight = height - PAD.top - PAD.bottom
  const xAt = (value: number) => box.xMin + ((value - PAD.left) / plotWidth) * (box.xMax - box.xMin)
  const yAt = (value: number) =>
    box.yMin + ((PAD.top + plotHeight - value) / plotHeight) * (box.yMax - box.yMin)
  return {
    xMin: shape.wide ? xAt(shape.left) : box.xMin,
    xMax: shape.wide ? xAt(shape.right) : box.xMax,
    yMin: shape.tall ? yAt(shape.bottom) : box.yMin,
    yMax: shape.tall ? yAt(shape.top) : box.yMax,
  }
}

/**
 * 이 x 에서 곡선의 y. **보간하지 않고 가장 가까운 점**을 쓴다.
 *
 * 보간하면 없는 값을 읽어 주게 된다 — 곡선 사이가 성기면 그 값이 어디서
 * 왔는지 아무도 답할 수 없다. 멀면 아예 안 읽는다.
 */
function at(points: [number, number][], x: number): number | null {
  let best: [number, number] | null = null
  let bestDistance = Infinity
  for (const point of points) {
    const distance = Math.abs(point[0] - x)
    if (distance < bestDistance) {
      bestDistance = distance
      best = point
    }
  }
  if (best === null) return null
  // 곡선이 그 자리에 없으면(구간 밖) 읽지 않는다.
  const span = points.length > 1 ? Math.abs(points[points.length - 1][0] - points[0][0]) : 0
  return span > 0 && bestDistance > span * 0.05 ? null : best[1]
}

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

/** 로그 축에 그릴 수 있는 점인가 — 로그 축에서는 양수만. */
function drawable(point: [number, number], logX: boolean, logY: boolean): boolean {
  return (!logX || point[0] > 0) && (!logY || point[1] > 0)
}

/**
 * 곡선을 SVG 경로로. **그릴 수 없는 점(로그 축의 0 이하)에서 펜을 든다** — 이어 그리면
 * 없는 선분이 생긴다.
 */
function pathOf(
  points: [number, number][],
  toX: (value: number) => number,
  toY: (value: number) => number,
  ok: (point: [number, number]) => boolean,
): string {
  let up = true
  const parts: string[] = []
  for (const point of points) {
    if (!ok(point)) {
      up = true
      continue
    }
    parts.push(`${up ? 'M' : 'L'}${toX(point[0])},${toY(point[1])}`)
    up = false
  }
  return parts.join(' ')
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
  logX: initialLogX = false,
  logY: initialLogY = false,
  marker,
}: CurveChartProps) {
  const [hover, setHover] = useState<number | null>(null)
  // **받은 로그 여부는 처음 축일 뿐** — 사람이 차트 위에서 바꾼다. 부르는 쪽이 바꾸면
  // (마스터커브 ↔ 원곡선 전환 등) 그 값으로 다시 선다.
  const [logX, setLogX] = useState(initialLogX)
  const [logY, setLogY] = useState(initialLogY)
  /**
   * 지금 보고 있는 범위. **`null` 이면 전체**다.
   *
   * 변환된 축(로그면 log10)에 담는다 — 확대·이동 계산이 전부 그 축에서
   * 일어나므로, 원래 값으로 들고 있으면 곱셈과 덧셈이 섞인다.
   */
  const [view, setView] = useState<Box | null>(null)
  // **축이 바뀌면 범위를 전체로** — 옛 범위는 다른 축의 값이다(2026-10-20 검토). 변형률
  // 0 ~ 0.003 을 확대한 채 X 축을 「시간」 으로 바꾸면 판이 거의 비었다. 부르는 쪽이 로그를
  // 바꿔도 같다 — 범위가 log10 좌표로 남는다.
  useEffect(() => {
    setLogX(initialLogX)
    setView(null)
  }, [initialLogX])
  useEffect(() => {
    setLogY(initialLogY)
    setView(null)
  }, [initialLogY])
  useEffect(() => setView(null), [xLabel, yLabel])
  const frame = useRef<SVGSVGElement>(null)
  /** 끌기 시작점. 놓을 때까지 들고 있는다. */
  const drag = useRef<{ x: number; y: number; box: Box } | null>(null)
  /**
   * 끌면 무엇을 하나. **기본은 영역 확대** — 「앞 구간을 펴서 보고 싶다」 가 요청이었다.
   * 이동은 확대한 뒤에 쓰는 일이라 바꿔서 쓴다.
   */
  const [tool, setTool] = useState<'zoom' | 'pan'>('zoom')
  /** 끌어 그리는 중인 사각형. */
  const [pick, setPick] = useState<Pick | null>(null)
  /** 휠 핸들러가 읽는 최신 범위. 핸들러는 한 번만 붙으므로 값을 참조로 넘긴다. */
  const viewRef = useRef<Box | null>(null)
  const wholeRef = useRef<Box | null>(null)

  // **네이티브로 붙인다.** React 의 `onWheel` 은 passive 라 `preventDefault`
  // 가 안 먹고, 그러면 확대할 때 판 전체가 함께 스크롤된다.
  //
  // **판이 생길 때 붙인다**(2026-10-20). 전에는 처음 그릴 때 한 번만 붙였는데, 시험 상세는
  // 곡선을 받기 전에 빈 점으로 먼저 그린다 — 그때 판이 없어 **휠이 끝내 안 붙었다.**
  const empty = points.length === 0
  useEffect(() => {
    const node = frame.current
    if (!node) return
    function wheel(event: WheelEvent) {
      if (!node) return
      event.preventDefault()
      // **Shift 를 누르면 가로만.** 브라우저가 Shift+휠을 가로 굴림(deltaX)으로 바꿔 보내기도 한다.
      const delta = event.deltaY || event.deltaX
      if (delta === 0) return
      const onlyX = event.shiftKey
      setView((current) => {
        const box = current ?? viewRef.current
        if (!box) return current
        const rect = node.getBoundingClientRect()
        // 커서가 가리키던 자리가 **그 자리에 남아야** 한다. 가운데를 기준으로
        // 당기면 보고 있던 곳이 화면 밖으로 밀려난다.
        const ax = (event.clientX - rect.left) / rect.width
        const ay = (event.clientY - rect.top) / rect.height
        const anchorX = box.xMin + (box.xMax - box.xMin) * plotShare(ax, 'x')
        const anchorY = box.yMax - (box.yMax - box.yMin) * plotShare(ay, 'y')
        const factor = delta < 0 ? WHEEL_STEP : 1 / WHEEL_STEP
        const yFactor = onlyX ? 1 : factor
        return clamp(
          {
            xMin: anchorX - (anchorX - box.xMin) * factor,
            xMax: anchorX + (box.xMax - anchorX) * factor,
            yMin: anchorY - (anchorY - box.yMin) * yFactor,
            yMax: anchorY + (box.yMax - anchorY) * yFactor,
          },
          wholeRef.current
        )
      })
    }
    node.addEventListener('wheel', wheel, { passive: false })
    return () => node.removeEventListener('wheel', wheel)
  }, [empty])

  const scale = useMemo(() => {
    if (points.length === 0) return null
    // 겹쳐 그리는 선도 축 범위에 넣는다. 안 넣으면 적합 곡선이 판을 벗어나
    // 잘려 보이고, 잘린 그림으로는 잘 맞는지 알 수 없다.
    const every = [
      ...points,
      ...(overlay?.points ?? []),
      ...(background ?? []).flatMap((one) => one.points),
    ]
    // 로그 축에 0 이하 점은 없다 — 넣으면 log10(0) 이 축을 수백 자릿수로 늘린다.
    const drawn = every.filter((point) => drawable(point, logX, logY))
    const all = drawn.length > 0 ? drawn : every
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
    // **확대한 범위가 있으면 그것이 이긴다.** 전체 범위는 「전체 보기」 로
    // 돌아갈 자리로 남는다.
    const box: Box = view ?? { xMin, xMax, yMin, yMax }
    const xSpan = box.xMax - box.xMin || 1
    const ySpan = box.yMax - box.yMin || 1
    const plotWidth = WIDTH - PAD.left - PAD.right
    const plotHeight = height - PAD.top - PAD.bottom
    return {
      xMin: box.xMin,
      xMax: box.xMax,
      yMin: box.yMin,
      yMax: box.yMax,
      /** 전체 범위. 「전체 보기」 와 확대 한계에 쓴다. */
      whole: { xMin, xMax, yMin, yMax } as Box,
      box,
      tx,
      ty,
      toX: (value: number) => PAD.left + ((tx(value) - box.xMin) / xSpan) * plotWidth,
      toY: (value: number) =>
        PAD.top + plotHeight - ((ty(value) - box.yMin) / ySpan) * plotHeight,
      // 눈금은 변환된 축에서 고르고, 자리와 라벨은 되돌려 쓴다.
      fromX: (value: number) => (logX ? 10 ** value : value),
      fromY: (value: number) => (logY ? 10 ** value : value),
      plotWidth,
      plotHeight,
      /** 로그 축이라 그리지 않은 점의 수. */
      hidden: every.length - drawn.length,
      /** 축마다 양수가 하나라도 있나 — 없으면 그 축은 로그로 못 바꾼다. */
      positiveX: every.some((point) => point[0] > 0),
      positiveY: every.some((point) => point[1] > 0),
    }
  }, [points, overlay, background, height, logX, logY, view])

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

  viewRef.current = scale.box
  wholeRef.current = scale.whole
  const zoomed = view !== null

  const ok = (point: [number, number]) => drawable(point, logX, logY)
  const path = pathOf(points, scale.toX, scale.toY, ok)
  const active = hover === null || !ok(points[hover]) ? null : points[hover]
  /** 눈금을 바꾸면 확대 범위(변환된 축의 값)가 뜻을 잃는다 — 전체로 돌린다. */
  const switchAxis = (axis: 'x' | 'y', log: boolean) => {
    setView(null)
    setHover(null)
    if (axis === 'x') setLogX(log)
    else setLogY(log)
  }

  /**
   * 마우스가 가리키는 x 에서 **각 곡선이 얼마인가.**
   *
   * 전에는 대표 곡선의 값 하나만 읽어 줬다. 뒤에 시편 열 개를 깔아 놓고 값은
   * 하나만 보여 주면, **흩어짐이 보이는데 얼마나 벌어졌는지는 못 읽는다.**
   */
  const readout =
    active === null
      ? []
      : [
          { label: pointsLabel ?? '대표', value: active[1], lead: true },
          ...(overlay ? [{ label: overlay.label, value: at(overlay.points, active[0]), lead: false }] : []),
          ...(background ?? []).map((one) => ({
            label: one.label,
            value: at(one.points, active[0]),
            lead: false,
          })),
        ].filter((row) => row.value !== null)

  return (
    <div className="rounded-md border p-2">
      {/* **확대하는 방법을 적어 둔다.** 굴려 보기 전에는 되는지 알 수 없고,
          안 되는 줄 알면 아무도 안 굴린다. */}
      <div className="text-muted-foreground mb-1 flex flex-wrap items-center gap-2 px-1 text-xs">
        <span title="Shift+휠은 가로만 확대합니다. 두 번 누르면 전체 보기로 돌아갑니다.">
          휠로 확대 ·{' '}
          {tool === 'zoom' ? '끌어서 영역 확대(옆으로만 끌면 가로만)' : '끌어서 이동'}
        </span>
        {/* **끌기가 하는 일을 고른다.** 영역 확대와 이동은 같은 손짓이라 한쪽만 줄 수 있다. */}
        <span className="inline-flex items-center gap-1" role="group" aria-label="끌기">
          <span>끌기</span>
          <span className="border-border inline-flex overflow-hidden rounded border">
            {(
              [
                ['zoom', '영역 확대'],
                ['pan', '이동'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={tool === key}
                className={`px-1.5 py-0.5 ${
                  tool === key ? 'bg-muted text-foreground font-medium' : 'hover:bg-muted/60'
                }`}
                onClick={() => setTool(key)}
              >
                {label}
              </button>
            ))}
          </span>
        </span>
        <AxisScaleToggle
          name="가로축"
          log={logX}
          disabled={!scale.positiveX}
          onChange={(log) => switchAxis('x', log)}
        />
        <AxisScaleToggle
          name="세로축"
          log={logY}
          disabled={!scale.positiveY}
          onChange={(log) => switchAxis('y', log)}
        />
        {scale.hidden > 0 && (
          <span className="text-amber-700 dark:text-amber-500">
            로그 눈금이라 0 이하 {scale.hidden}점은 그리지 않았습니다
          </span>
        )}
        {zoomed && (
          <>
            <span className="text-foreground tabular-nums">
              x {format(scale.fromX(scale.xMin))} ~ {format(scale.fromX(scale.xMax))}
            </span>
            <button
              type="button"
              className="border-border hover:bg-muted ml-auto rounded border px-1.5 py-0.5"
              onClick={() => setView(null)}
            >
              전체 보기
            </button>
          </>
        )}
      </div>
      <svg
        ref={frame}
        viewBox={`0 0 ${WIDTH} ${height}`}
        className={`w-full select-none ${
          tool === 'zoom' ? 'cursor-crosshair' : zoomed ? 'cursor-grab' : ''
        }`}
        role="img"
        aria-label={`${yLabel} 대 ${xLabel} 곡선`}
        onMouseLeave={() => {
          setHover(null)
          drag.current = null
          // 판 밖에서 놓으면 놓은 줄 모른다 — 고르던 것은 버린다.
          setPick(null)
        }}
        onMouseDown={(event) => {
          if (event.button !== 0) return
          if (tool === 'zoom') {
            const rect = event.currentTarget.getBoundingClientRect()
            const x = ((event.clientX - rect.left) / rect.width) * WIDTH
            const y = ((event.clientY - rect.top) / rect.height) * height
            setHover(null)
            setPick({ x0: x, y0: y, x1: x, y1: y })
            return
          }
          // 확대했을 때만 끌어 옮긴다 — 전체를 보고 있으면 옮길 데가 없다.
          if (!zoomed) return
          drag.current = { x: event.clientX, y: event.clientY, box: scale.box }
        }}
        onMouseUp={() => {
          drag.current = null
          if (pick) {
            const next = pickBox(pick, scale.box, height)
            setPick(null)
            if (next) setView(clamp(next, scale.whole))
          }
        }}
        // **두 번 누르면 전체로.** 확대를 거듭하다 길을 잃었을 때 단추를 찾지 않아도 된다.
        onDoubleClick={() => setView(null)}
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect()
          if (pick) {
            setPick({
              ...pick,
              x1: ((event.clientX - box.left) / box.width) * WIDTH,
              y1: ((event.clientY - box.top) / box.height) * height,
            })
            return
          }
          const held = drag.current
          if (held) {
            // 끌린 만큼 **범위를 반대로** 옮긴다. 손이 데이터를 잡고 있는 느낌이
            // 되려면 그래야 한다. **판(plot)의 폭으로 나눈다** — 그림 전체 폭(축 여백 포함)
            // 으로 나누면 데이터가 손보다 약 12 % 덜 따라왔다(2026-10-20 검토).
            const dx =
              ((((event.clientX - held.x) / box.width) * WIDTH) / scale.plotWidth) *
              (held.box.xMax - held.box.xMin)
            const dy =
              ((((event.clientY - held.y) / box.height) * height) / scale.plotHeight) *
              (held.box.yMax - held.box.yMin)
            setView(
              clamp(
                {
                  xMin: held.box.xMin - dx,
                  xMax: held.box.xMax - dx,
                  yMin: held.box.yMin + dy,
                  yMax: held.box.yMax + dy,
                },
                scale.whole
              )
            )
            return
          }
          const svgX = ((event.clientX - box.left) / box.width) * WIDTH
          // 가장 가까운 점 하나를 고른다. 보간하면 없는 값을 읽어 주게 된다.
          let best = 0
          let bestDistance = Infinity
          points.forEach((p, index) => {
            if (!ok(p)) return
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

        {marker !== undefined && (!logX || marker.x > 0) && (
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
            d={pathOf(one.points, scale.toX, scale.toY, ok)}
            fill="none"
            // **흐리되 보여야 한다.** 30% 회색 1px 로 뒀더니 대표선 아래에서
            // 사실상 안 보였고, 그러면 이 선을 그리는 뜻이 없다.
            className={one.tone ?? 'stroke-sky-600 dark:stroke-sky-400'}
            strokeWidth={one.dashed ? 1.4 : 1.1}
            strokeDasharray={one.dashed ? '4 3' : undefined}
            opacity={one.dashed ? 0.8 : 0.45}
          >
            <title>{one.label}</title>
          </path>
        ))}

        <path d={path} fill="none" className="stroke-primary" strokeWidth={1.75} />

        {overlay && overlay.points.length > 0 && (
          <path
            d={pathOf(overlay.points, scale.toX, scale.toY, ok)}
            fill="none"
            className="stroke-amber-600 dark:stroke-amber-500"
            strokeWidth={1.75}
            strokeDasharray="5 3"
          />
        )}

        {(() => {
          // 놓으면 펼 모양 그대로 보인다 — 얇게 끌면 판 높이 전체(가로만)로.
          const shape = pick ? pickShape(pick, height) : null
          if (!shape) return null
          return (
            <rect
              data-testid="zoom-pick"
              x={shape.left}
              y={shape.top}
              width={shape.right - shape.left}
              height={shape.bottom - shape.top}
              className="fill-primary/10 stroke-primary"
              strokeDasharray="4 3"
            />
          )
        })()}

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

      {readout.length > 1 && (
        // **여러 곡선을 깔아 놓고 값은 하나만 보여 주면** 흩어짐이 보이는데
        // 얼마나 벌어졌는지는 못 읽는다. 가리킨 x 에서 전부 읽어 준다.
        <div className="mt-1 border-t pt-1">
          <p className="text-muted-foreground mb-0.5 px-1 text-[11px]">
            {xLabel} = <b className="text-foreground tabular-nums">{format(active![0])}</b> 에서
          </p>
          <ul className="grid grid-cols-2 gap-x-3 px-1 text-[11px] sm:grid-cols-3">
            {readout.map((row) => (
              <li
                key={row.label}
                className={`flex justify-between gap-2 ${row.lead ? 'text-foreground font-medium' : 'text-muted-foreground'}`}
              >
                <span className="truncate" title={row.label}>
                  {row.lead ? row.label : row.label.slice(-11)}
                </span>
                <span className="tabular-nums">{format(row.value as number)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

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
