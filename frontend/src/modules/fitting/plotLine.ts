/**
 * 블록 그래프의 **계수 선** — 선언(`plot.line`)과 값으로 점을 낸다(SI, 화면 단위로 바꾸기 전).
 *
 * `y = c · x^e`. `knee` · `exponent2` 가 있으면 그 x 부터 둘째 지수로 **이어서**
 * `y = c · k^e · (x/k)^e2` — 2구간 S-N(꺾임 수명 Nc1 · 둘째 기울기 b2, 2026-11-14). 선은 점이 있는
 * x 범위만 그리고(외삽하지 않는다), 꺾임이 그 안에 있으면 그 자리를 그대로 지난다 — 고르게 놓은
 * 점 사이에 있으면 모서리가 깎여 보인다.
 */

import type { components } from '@/shared/api/schema'

type BlockPlot = components['schemas']['BlockPlotOut']

/** 계수 선을 몇 점으로 그리나. 로그 축에서 자릿수마다 고르게. */
export const LINE_POINTS = 60

export function plotLine(
  plot: BlockPlot,
  values: Record<string, unknown>,
  low: number,
  high: number
): [number, number][] {
  const line = plot.line
  if (!line) return []
  const coefficient = Number(values[line.coefficient])
  const exponent = Number(values[line.exponent])
  if (!Number.isFinite(coefficient) || !Number.isFinite(exponent)) return []
  if (!(high >= low) || (plot.log_x && low <= 0)) return []
  const knee = line.knee ? Number(values[line.knee]) : NaN
  const exponent2 = line.exponent2 ? Number(values[line.exponent2]) : NaN
  const bent = Number.isFinite(knee) && knee > 0 && Number.isFinite(exponent2)
  const at = (x: number) =>
    bent && x > knee
      ? coefficient * knee ** exponent * (x / knee) ** exponent2
      : coefficient * x ** exponent

  const xs: number[] = []
  for (let index = 0; index < LINE_POINTS; index += 1) {
    const share = index / (LINE_POINTS - 1)
    xs.push(
      plot.log_x
        ? 10 ** (Math.log10(low) + (Math.log10(high) - Math.log10(low)) * share)
        : low + (high - low) * share
    )
  }
  if (bent && knee > low && knee < high) xs.push(knee)
  xs.sort((a, b) => a - b)
  return xs.map((x) => [x, at(x)])
}
