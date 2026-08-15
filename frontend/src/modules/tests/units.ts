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

/**
 * 조건 입력이 **화면에서 어떤 단위로 받아지는지**. 업로드할 때 값과 함께 보낸다.
 *
 * 이것을 안 보내던 때 실제로 사고가 났다: 라벨은 `탄성역 속도 (mm/min)` 인데 값은
 * 그대로 보내서, 서버가 정의의 `si_unit`(m/s)으로 해석해 **6만 배** 어긋난 값을
 * 저장했다. 숫자가 그럴듯해 보여 화면 어디에도 티가 나지 않는다.
 *
 * 변환은 여전히 서버가 한다 — 화면은 "내가 받은 단위는 이것" 이라고 말할 뿐이다.
 */
export function conditionUnits(fields: { key: string; si_unit?: string | null }[]) {
  const map: Record<string, string> = {}
  for (const field of fields) {
    if (!field.si_unit) continue
    const { unit } = display(field.si_unit)
    if (unit) map[field.key] = unit
  }
  return map
}

/**
 * 편집 화면이 고르게 할 차원과 단위. **서버의 `matcore/units` 표를 좁혀 옮긴 것**
 * 이므로 거기에 없는 단위를 넣으면 저장할 때 거절당한다.
 *
 * 완전한 복제가 아니라 자주 쓰는 것만 둔다 — 목록이 길면 고르기 어렵고, 서버가
 * 최종 판정을 하므로 화면이 전부 알 필요는 없다.
 */
export const UNITS_BY_DIMENSION: Record<string, string[]> = {
  length: ['m', 'mm', 'cm', 'um'],
  force: ['N', 'kN'],
  stress: ['Pa', 'kPa', 'MPa', 'GPa'],
  strain: ['1', '%'],
  strain_rate: ['1/s', '1/min'],
  velocity: ['m/s', 'mm/s', 'mm/min'],
  time: ['s', 'ms', 'min', 'h'],
  temperature: ['K', 'degC'],
  frequency: ['Hz', 'kHz'],
  mass: ['kg', 'g', 'tonne'],
  angle: ['rad', 'deg'],
  dimensionless: ['1'],
}

export const DIMENSIONS = Object.keys(UNITS_BY_DIMENSION)

export const VALUE_TYPES = [
  { value: 'number', label: '숫자' },
  { value: 'text', label: '문자' },
  { value: 'choice', label: '선택' },
  { value: 'date', label: '날짜' },
  { value: 'boolean', label: '예/아니오' },
] as const
