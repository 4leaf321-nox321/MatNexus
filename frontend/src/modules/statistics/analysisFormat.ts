/**
 * 물성 분석의 값 표시 — **탭 여럿이 같은 자릿수 규칙을 쓴다.**
 *
 * 비교·분포·추이의 표와 「카드 항목」 의 값 목록이 같은 숫자를 다르게 적으면, 같은
 * 탄성계수가 탭마다 다른 값으로 읽힌다.
 */

import { display, toDisplay } from '@/shared/units'

/** SI 값을 표시 단위로. **자릿수는 크기에 맞춘다** — 0.0000002 도 200000 도 안 읽힌다. */
export function show(value: number, siUnit: string): string {
  const shown = toDisplay(value, siUnit)
  const size = Math.abs(shown)
  if (size === 0) return '0'
  if (size >= 1000) return shown.toFixed(0)
  if (size >= 10) return shown.toFixed(1)
  if (size >= 0.1) return shown.toFixed(3)
  return shown.toPrecision(3)
}

/**
 * 값 옆에 단위 — `320.0 MPa`. **머리에 단위를 못 두는 표**에서 쓴다: 줄마다 항목(과
 * 단위)이 다른 「선언 vs 실측」, 열이 연도인 「추이」. 단위가 어디에도 없으면 숫자가
 * Pa 인지 MPa 인지 사람이 짐작해야 한다(2026-09-14 지적).
 */
export function showWithUnit(value: number, siUnit: string): string {
  const { unit } = display(siUnit)
  return unit ? `${show(value, siUnit)} ${unit}` : show(value, siUnit)
}

/** 분석 표의 칸 여백 — 탭마다 같은 표로 보이게. */
export const TABLE_PAD =
  '[&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-4 [&_th:first-child]:pl-4 ' +
  '[&_td:last-child]:pr-4 [&_th:last-child]:pr-4'
