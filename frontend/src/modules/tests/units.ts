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
  /**
   * 곱한 뒤 더한다 — `표시 = SI × factor + offset`.
   *
   * **온도 때문에 필요하다.** 다른 단위는 전부 비례라 배수 하나면 되는데,
   * 섭씨만 원점이 다르다. 오프셋이 없던 동안 DMA 곡선의 온도축이 `298 K` 로
   * 나왔고, 실무에서 그렇게 읽는 사람은 없다.
   */
  offset: number
}

const BY_SI: Record<string, Display> = {
  m: { unit: 'mm', factor: 1000, offset: 0 },
  // 단면적. CAE 입력은 mm² 다 — 1e-5 를 치라고 하면 사람이 자릿수를 센다.
  m2: { unit: 'mm²', factor: 1e6, offset: 0 },
  N: { unit: 'N', factor: 1, offset: 0 },
  Pa: { unit: 'MPa', factor: 1e-6, offset: 0 },
  // 섭씨만 원점이 다르다. 백엔드는 진작 오프셋을 갖고 있었고
  // (`matcore/units.py` 의 `degC`), 화면에만 없었다.
  K: { unit: '°C', factor: 1, offset: -273.15 },
  Hz: { unit: 'Hz', factor: 1, offset: 0 },
  s: { unit: 's', factor: 1, offset: 0 },
  'm/s': { unit: 'mm/min', factor: 60000, offset: 0 },
  '1/s': { unit: '1/s', factor: 1, offset: 0 },
  'kg/m3': { unit: 'kg/m³', factor: 1, offset: 0 },
  '1': { unit: '', factor: 1, offset: 0 },
}

/**
 * 단위로는 못 가르고 **차원으로만** 갈리는 것.
 *
 * 변형률과 tan δ 는 저장 단위가 둘 다 `1` 이다 — 물리적으로 둘 다 무차원이라
 * 맞다. 그런데 물성에서 변형률은 2% 로 읽지 0.02 로 읽지 않고, tan δ 는 그 반대다.
 * 단위만 보면 구분할 방법이 없다.
 *
 * `strain` 을 `dimensionless` 의 **별칭 차원**으로 남겨 둔 이유가 이것이다
 * (`matcore/units.DIMENSION_ALIASES`). 차원 검증에서는 같은 것으로 치지만,
 * 사람에게 보여 줄 때는 뜻이 다르다.
 */
const BY_DIMENSION: Record<string, Display> = {
  strain: { unit: '%', factor: 100, offset: 0 },
}

export function display(
  siUnit: string | null | undefined,
  dimension?: string | null
): Display {
  if (dimension) {
    const byDimension = BY_DIMENSION[dimension]
    if (byDimension) return byDimension
  }
  if (!siUnit) return { unit: '', factor: 1, offset: 0 }
  return BY_SI[siUnit] ?? { unit: siUnit, factor: 1, offset: 0 }
}

/** 축 라벨 — `변위 (mm)`. 단위가 없으면 괄호도 없다. */
export function axisLabel(
  label: string,
  siUnit: string | null | undefined,
  dimension?: string | null
): string {
  const { unit } = display(siUnit, dimension)
  return unit ? `${label} (${unit})` : label
}

export function toDisplay(
  value: number,
  siUnit: string | null | undefined,
  dimension?: string | null
): number {
  const { factor, offset } = display(siUnit, dimension)
  return value * factor + offset
}

/**
 * 표시 값 → SI. `toDisplay` 의 역이다.
 *
 * 오프셋이 생긴 뒤로는 **나누기만 해서는 안 된다.** 25 °C 를 25 K 로 보내면
 * -248 °C 다. 두 함수를 짝으로 두는 이유가 이것이다.
 */
export function fromDisplay(
  value: number,
  siUnit: string | null | undefined,
  dimension?: string | null
): number {
  const { factor, offset } = display(siUnit, dimension)
  return (value - offset) / factor
}

/**
 * **차이(Δ)는 오프셋을 빼지 않는다.**
 *
 * 온도 차 10 K 는 10 °C 이지 -263 °C 가 아니다. 65도 같은 것을 갖고 있었다
 * (`quantity_semantics == "temperature.difference"` 면 오프셋을 건너뛴다).
 * 지금은 차이를 표시하는 자리가 없지만, 생기는 순간 이 함수를 써야 한다 —
 * 안 쓰면 273.15 만큼 어긋난 값이 그럴듯하게 나온다.
 */
export function spanToDisplay(
  value: number,
  siUnit: string | null | undefined,
  dimension?: string | null
): number {
  return value * display(siUnit, dimension).factor
}

/** 요약값 한 줄을 사람이 읽는 문자열로. */
export function formatValue(
  value: number | null,
  text: string | null,
  siUnit: string | null,
  dimension?: string | null
): string {
  if (value === null) return text ?? '—'
  const { unit, factor, offset } = display(siUnit, dimension)
  const shown = value * factor + offset
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
export function conditionUnits(
  fields: { key: string; si_unit?: string | null; dimension?: string | null }[]
) {
  const map: Record<string, string> = {}
  for (const field of fields) {
    if (!field.si_unit) continue
    const { unit } = display(field.si_unit, field.dimension)
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
/**
 * 차원별 **저장 단위**. 고르는 것이 아니라 정해져 있다.
 *
 * 값은 언제나 그 차원의 정본 SI 로 저장된다. 정의에 `MPa` 라고 적으면 저장된
 * 숫자는 Pa 인데 화면은 MPa 로 읽어 10⁶ 배 틀린다 — 서버도 이것을 거절한다.
 */
export const SI_BY_DIMENSION: Record<string, string> = {
  length: 'm',
  force: 'N',
  stress: 'Pa',
  strain: '1',
  strain_rate: '1/s',
  velocity: 'm/s',
  time: 's',
  temperature: 'K',
  frequency: 'Hz',
  angular_frequency: 'rad/s',
  inverse_temperature: '1/K',
  compliance: '1/Pa',
  mass: 'kg',
  density: 'kg/m3',
  angle: 'rad',
  dimensionless: '1',
}

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
  // DMA 가 각주파수를 준다. 이것이 빠져 있어서 화면에서 DMA 종류를 만들 수 없었다.
  angular_frequency: ['rad/s'],
  inverse_temperature: ['1/K'],
  compliance: ['1/Pa', '1/MPa'],
  mass: ['kg', 'g', 'tonne'],
  density: ['kg/m3', 'g/cm3', 'tonne/mm3'],
  angle: ['rad', 'deg'],
  dimensionless: ['1'],
}

/** 서버 `matcore.units.SI_UNITS` 의 16차원과 같아야 한다. 어긋나면 정의 저장을
 *  서버가 거절하므로 **조용히 틀리지는 않는다** — 화면에서 바로 드러난다. */
export const DIMENSIONS = Object.keys(UNITS_BY_DIMENSION)

export const VALUE_TYPES = [
  { value: 'number', label: '숫자' },
  { value: 'text', label: '문자' },
  { value: 'choice', label: '선택' },
  { value: 'date', label: '날짜' },
  { value: 'boolean', label: '예/아니오' },
] as const


/**
 * 값 하나를 사람이 읽는 문자열로 — **자릿수까지 골라 준다.**
 *
 * `formatValue` 와 다른 점: 응력은 크기에 따라 MPa/GPa 를 오간다. 205000 MPa 로
 * 적힌 탄성계수는 아무도 안 읽는다.
 *
 * **이 함수가 없어서 같은 코드가 세 번 복제돼 있었다**(처리 패널·결과 목록·배치
 * 다이얼로그). 셋 다 `value / 1e6` 을 손으로 적었고, 셋 다 **Pa 만 알았다** —
 * 스칼라가 m 나 K 로 오면 SI 그대로 나왔다. 환산 규칙이 여러 곳에 있으면
 * 언젠가 갈라진다는 것이 이 파일의 첫 줄에 적혀 있다.
 */
export function formatScalar(
  value: number,
  siUnit: string | null | undefined,
  dimension?: string | null
): string {
  // 응력만 예외다. GPa 까지 올라가는 것은 탄성계수뿐이고, 그 값을 MPa 로 적으면
  // 205000 이 된다.
  if (siUnit === 'Pa' && Math.abs(value) >= 1e9) {
    return `${Number((value / 1e9).toPrecision(4))} GPa`
  }
  const { unit, factor, offset } = display(siUnit, dimension)
  const shown = value * factor + offset
  const magnitude = Math.abs(shown)
  const text =
    magnitude === 0
      ? '0'
      : magnitude >= 100000 || magnitude < 0.001
        ? shown.toExponential(3)
        : String(Number(shown.toPrecision(5)))
  return unit ? `${text} ${unit}` : text
}
