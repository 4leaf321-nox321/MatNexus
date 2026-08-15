/**
 * 표시 단위 — 저장은 SI, 화면은 실무 단위.
 *
 * 서버는 SI 로 준다(m·N·Pa·K). 그대로 그리면 변위가 `0.0200037` 로 보이고, 그런
 * 숫자는 아무도 읽지 않는다. 여기서 표시용으로만 되돌린다.
 *
 * **환산은 화면에서만 한다.** 값을 서버로 보낼 때는 원래 단위를 명시해 보내고
 * 서버가 SI 로 바꾼다 — 변환 규칙이 두 곳에 있으면 언젠가 갈라진다(ADR 0004).
 */

export interface Display {
  unit: string
  /** SI 값에 곱해 표시 값으로 만든다. */
  factor: number
}

const BY_SI: Record<string, Display> = {
  m: { unit: 'mm', factor: 1000 },
  N: { unit: 'N', factor: 1 },
  Pa: { unit: 'MPa', factor: 1e-6 },
  K: { unit: 'K', factor: 1 },
  Hz: { unit: 'Hz', factor: 1 },
  s: { unit: 's', factor: 1 },
  'm/s': { unit: 'mm/min', factor: 60000 },
  '1/s': { unit: '1/s', factor: 1 },
  'kg/m3': { unit: 'kg/m³', factor: 1 },
  '1': { unit: '', factor: 1 },
}

export function display(siUnit: string | null | undefined): Display {
  if (!siUnit) return { unit: '', factor: 1 }
  return BY_SI[siUnit] ?? { unit: siUnit, factor: 1 }
}

/** 축 라벨 — `변위 (mm)`. 단위가 없으면 괄호도 없다. */
export function axisLabel(label: string, siUnit: string | null | undefined): string {
  const { unit } = display(siUnit)
  return unit ? `${label} (${unit})` : label
}

export function toDisplay(value: number, siUnit: string | null | undefined): number {
  return value * display(siUnit).factor
}

/** 요약값 한 줄을 사람이 읽는 문자열로. */
export function formatValue(
  value: number | null,
  text: string | null,
  siUnit: string | null
): string {
  if (value === null) return text ?? '—'
  const { unit, factor } = display(siUnit)
  const shown = value * factor
  const magnitude = Math.abs(shown)
  const rounded =
    magnitude === 0
      ? '0'
      : magnitude >= 10000 || magnitude < 0.001
        ? shown.toExponential(3)
        : Number(shown.toPrecision(5)).toString()
  return unit ? `${rounded} ${unit}` : rounded
}
