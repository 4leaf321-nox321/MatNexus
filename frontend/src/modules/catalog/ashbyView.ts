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
