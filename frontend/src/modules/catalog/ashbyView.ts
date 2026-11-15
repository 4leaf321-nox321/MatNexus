/**
 * Ashby 지도의 **보는 범위** 계산 — 확대 · 이동 · 화면 좌표 환산(2026-11-15, VOC 41 a 후속).
 *
 * 그림과 떼어 둔 까닭: jsdom 은 크기를 0 으로 주어 화면에서 시험하면 계산이 아니라 흉내 낸
 * 크기를 보게 된다. 숫자만 받는 함수로 두면 **커서 자리가 정말 그 자리에 남는지**를 그대로 잰다 —
 * 곡선 차트는 세로 여백을 빼지 않아 가리킨 값이 판 밖으로 나갔고, 이동이 데이터 밖으로 나갔다
 * (2026-11-14 검토). 같은 결함을 베끼지 않으려고 둘 다 시험으로 묶는다.
 *
 * 좌표는 **축에 그리는 값**(로그축이면 log10)이다.
 */

export interface Box {
  x0: number
  x1: number
  y0: number
  y1: number
}

/** 전체의 몇 분의 일까지 좁힐 수 있나. */
export const MAX_ZOOM = 500

/** 폭을 지킨 채 [floor, ceiling] 안으로 민다. 전체보다 넓으면 전체. */
function within(low: number, high: number, floor: number, ceiling: number): [number, number] {
  const span = high - low
  if (span >= ceiling - floor) return [floor, ceiling]
  if (low < floor) return [floor, floor + span]
  if (high > ceiling) return [ceiling - span, ceiling]
  return [low, high]
}

/** 범위를 전체 안에 두고 너무 파고들지 못하게 한다. 전체와 같아지면 `null`(전체 보기). */
export function settle(box: Box, full: Box): Box | null {
  let { x0, x1, y0, y1 } = box
  const minX = (full.x1 - full.x0) / MAX_ZOOM
  const minY = (full.y1 - full.y0) / MAX_ZOOM
  if (x1 - x0 < minX) {
    const mid = (x0 + x1) / 2
    ;[x0, x1] = [mid - minX / 2, mid + minX / 2]
  }
  if (y1 - y0 < minY) {
    const mid = (y0 + y1) / 2
    ;[y0, y1] = [mid - minY / 2, mid + minY / 2]
  }
  ;[x0, x1] = within(x0, x1, full.x0, full.x1)
  ;[y0, y1] = within(y0, y1, full.y0, full.y1)
  if (x0 === full.x0 && x1 === full.x1 && y0 === full.y0 && y1 === full.y1) return null
  return { x0, x1, y0, y1 }
}

/**
 * 커서가 가리킨 자리를 **그 자리에 둔 채** 당기거나 민다. `shareX` · `shareY` 는 판(plot) 안에서의
 * 비율(왼쪽 · 아래가 0) — 여백을 뺀 값이어야 한다.
 */
export function zoomAt(
  box: Box,
  full: Box,
  shareX: number,
  shareY: number,
  factor: number
): Box | null {
  const ax = box.x0 + (box.x1 - box.x0) * shareX
  const ay = box.y0 + (box.y1 - box.y0) * shareY
  return settle(
    {
      x0: ax - (ax - box.x0) * factor,
      x1: ax + (box.x1 - ax) * factor,
      y0: ay - (ay - box.y0) * factor,
      y1: ay + (box.y1 - ay) * factor,
    },
    full
  )
}

/** 판의 비율만큼 끌었다 — 손이 데이터를 잡은 것처럼 범위를 반대로 옮긴다. */
export function panBy(box: Box, full: Box, shareX: number, shareY: number): Box | null {
  const dx = (box.x1 - box.x0) * shareX
  const dy = (box.y1 - box.y0) * shareY
  return settle({ x0: box.x0 - dx, x1: box.x1 - dx, y0: box.y0 - dy, y1: box.y1 - dy }, full)
}

/**
 * 화면 좌표 → viewBox 좌표. SVG 는 비율을 지키며 가운데에 그리므로(`meet`), 그림틀이 viewBox 와
 * 비율이 다르면 양옆이나 위아래가 빈다 — 틀의 비율로만 나누면 그만큼 어긋난다(폭 1200 · 높이
 * 520 인 틀에서 가장자리가 폭의 11 %).
 */
export function toViewBox(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  width: number,
  height: number
): [number, number] | null {
  const scale = Math.min(rect.width / width, rect.height / height)
  if (!(scale > 0)) return null
  const offsetX = (rect.width - width * scale) / 2
  const offsetY = (rect.height - height * scale) / 2
  return [(clientX - rect.left - offsetX) / scale, (clientY - rect.top - offsetY) / scale]
}

/** 보는 범위 안에 이만큼은 눈금이 서야 값을 읽는다 — 하나면 어느 쪽으로 늘어나는지 모른다. */
const MIN_TICKS = 3

/** 로그축 한 자릿수 안의 눈금 — 10 배만 · 1·2·5 · 1~9. 차례대로 촘촘해진다. */
const LOG_STEPS = [[1], [1, 2, 5], [1, 2, 3, 4, 5, 6, 7, 8, 9]]

function linearTicks(min: number, max: number): number[] {
  const span = max - min || 1
  const step = 10 ** Math.floor(Math.log10(span / 4))
  const nice = [step, step * 2, step * 5, step * 10].find((one) => span / one <= 6) ?? step
  const start = Math.ceil(min / nice) * nice
  const out: number[] = []
  for (let tick = start; tick <= max; tick += nice) out.push(tick)
  return out
}

/**
 * 축 눈금 — `min` · `max` 는 **보는 범위의 값**(로그축이어도 값, log10 이 아니다).
 *
 * 로그축은 10 배마다 하나였다. 한 자릿수 안으로 당기면 눈금이 하나만 남았다(2026-11-15 점검:
 * 3e-10 ~ 2e-9 에서 1e-9 하나) — 어느 쪽이 큰지조차 안 보인다. 그래서 범위 안에 `MIN_TICKS` 가
 * 안 서면 2 · 5 를, 그래도 모자라면 1~9 를 더하고, 한 자릿수의 몇 분의 일까지 당기면(로그와
 * 선형이 거의 같다) 선형 눈금으로 간다. 범위 밖 눈금도 돌려준다 — 그리는 쪽이 판 밖을 거른다.
 */
export function axisTicks(min: number, max: number, log: boolean): number[] {
  if (!log) return linearTicks(min, max)
  const lo = Math.floor(Math.log10(min))
  const hi = Math.ceil(Math.log10(max))
  const inside = (ticks: number[]) =>
    ticks.filter((tick) => tick >= min * (1 - 1e-9) && tick <= max * (1 + 1e-9)).length
  for (const steps of LOG_STEPS) {
    const ticks: number[] = []
    for (let exponent = lo; exponent <= hi; exponent += 1) {
      // 곱한 끝자리 흔들림(3 × 1e-10 = 3.0000000000000004e-10)을 지운다 — 눈금 이름이 갈린다.
      for (const step of steps) ticks.push(Number((step * 10 ** exponent).toPrecision(12)))
    }
    if (inside(ticks) >= MIN_TICKS) return ticks
  }
  return linearTicks(min, max)
}

/**
 * 눈금 · 점의 값 글자. 아주 크거나 작으면 지수로 — **가려지는 만큼만 자릿수를 둔다**: 선형
 * 눈금으로 넘어간 좁은 범위(3.1e-10 · 3.2e-10)가 전에는 둘 다 `3e-10` 이었다.
 */
export function tickLabel(value: number): string {
  const magnitude = Math.abs(value)
  if (magnitude !== 0 && (magnitude >= 1e4 || magnitude < 1e-2)) {
    return Number(value.toPrecision(4)).toExponential()
  }
  return String(Number(value.toPrecision(3)))
}
