/**
 * 처리 순서도 — **이 시점에 무엇이 있고, 이 단계를 지금 쓸 수 있는가.**
 *
 * ## 왜 필요했나
 *
 * 장비가 주는 것은 변위·하중·폭뿐이다. 응력도 변형률도 **앞 단계가 만든다.**
 * 그런데 화면은 "한 번 돌려 본 결과의 열" 만 알고 있어서, 돌려 보기 전에는
 * 인장강도 단계의 '변형률 열' 목록이 비어 있었다 — **돌려 보려면 골라야 하고,
 * 고르려면 돌려 봐야 하는** 자리였다.
 *
 * 이제 계산이 자기 의존을 선언한다(`makes_columns`·`makes_values`·`order`).
 * 여기서는 그 선언을 순서대로 접어(fold) "N번째 단계 앞에 존재하는 열·값" 을
 * 낸다. 서버를 부르지 않고 안다.
 *
 * ## 순서를 화면이 정하지 않는다
 *
 * 권장 순서는 `order` 로 서버가 준다. 순서는 계산의 성질이다 — 공칭 변환 없이는
 * 변형률 열이 없고, 재샘플을 앞에 두면 뒤 계산이 전부 보간된 점으로 돈다.
 * 화면에 적으면 계산을 고칠 때 두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
 */

import { isReference, isUsed, referenceLabel } from '@/modules/processing/api'
import type {
  Produced,
  ProcessingScalar,
  ProcessingStep,
  RecipeStep,
} from '@/modules/processing/api'
import { display, toDisplay } from '@/shared/units'

/**
 * 바깥에서 들어오는 값. **단계가 만드는 것이 아니다.**
 *
 * 시편 치수는 곡선에 없고 시편 기록에 있다. 서버가 `given` 으로 넣어 준다 —
 * 이것을 "앞 단계가 만들어야 하는 값" 으로 세면 첫 단계부터 막힌다.
 */
const FROM_SPECIMEN = 'specimen_'

/** `{column}_smoothed` 같은 틀을 그 단계의 옵션 값으로 채운다. */
export function resolveTemplate(template: string, options: Record<string, unknown>): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = options[name]
    return value === undefined || value === null ? whole : String(value)
  })
}

/**
 * 이 단계가 새로 더하는 열. 옵션에 따라 **이름이 달라지는 것**도 있어서, 선언을
 * 그대로 주지 않고 그 단계 옵션으로 채워서 낸다.
 */
export function madeColumns(step: RecipeStep, catalog: Map<string, ProcessingStep>): Produced[] {
  const plugin = catalog.get(step.plugin)
  return (plugin?.makes_columns ?? []).map((item) => ({
    ...item,
    key: resolveTemplate(item.key, step.options),
  }))
}

/**
 * `index` 번째 단계를 **시작하기 직전**에 프레임에 있는 열.
 *
 * `index` 가 단계 수와 같으면 파이프라인이 끝난 뒤의 열이다.
 */
export function columnsAt(
  steps: RecipeStep[],
  index: number,
  source: string[],
  catalog: Map<string, ProcessingStep>
): string[] {
  const seen = new Set(source)
  for (const step of steps.slice(0, index)) {
    for (const item of madeColumns(step, catalog)) seen.add(item.key)
  }
  return [...seen]
}

/** `index` 번째 단계 직전에 쓸 수 있는 값(스칼라) 키. */
export function valuesAt(
  steps: RecipeStep[],
  index: number,
  catalog: Map<string, ProcessingStep>
): Set<string> {
  const seen = new Set<string>()
  for (const step of steps.slice(0, index)) {
    for (const item of catalog.get(step.plugin)?.makes_values ?? []) seen.add(item.key)
  }
  return seen
}

export interface Blocker {
  /** 사람이 읽는 이유. 그대로 화면에 뜬다. */
  reason: string
  /** 이걸 풀어 주는 단계. 있으면 "○○를 먼저 넣으세요" 로 안내한다. */
  fixedBy?: string
}

/**
 * 지금 이 자리에서 이 단계가 **돌 수 없는 이유**.
 *
 * 비어 있으면 돌 수 있다. **막지는 않는다** — 이유를 말하고 회색으로 둔다.
 * 서버가 최종 판정을 하고, 여기 판정이 틀려도 계산이 조용히 이상해지지는
 * 않는다(서버는 없는 열을 받으면 실패한다).
 */
export function blockersAt(
  step: RecipeStep,
  index: number,
  steps: RecipeStep[],
  source: string[],
  catalog: Map<string, ProcessingStep>
): Blocker[] {
  const plugin = catalog.get(step.plugin)
  if (!plugin) return [{ reason: `등록되지 않은 단계입니다: ${step.plugin}` }]

  const columns = new Set(columnsAt(steps, index, source, catalog))
  const values = valuesAt(steps, index, catalog)
  const found: Blocker[] = []

  for (const param of plugin.params) {
    // 지금 안 쓰이는 칸은 비어 있어도 된다. 방법이 '최소제곱 회귀' 면
    // '직접 입력' 칸은 아무 데도 안 쓰인다.
    if (!isUsed(param, step.options)) continue

    const value = step.options[param.name] ?? param.default
    const empty = value === null || value === undefined || value === ''

    // **비면 계산이 실패하는 칸.** 어느 칸이 그런지는 계산이 선언한다
    // (`ParamSpec.required`) — 화면이 추측하면 멀쩡한 구성을 붉게 칠한다.
    if (param.required && empty && param.role !== 'column') {
      found.push({ reason: `${param.label}을(를) 채워야 합니다.` })
      continue
    }

    if (param.role === 'column') {
      if (empty) {
        found.push({ reason: `${param.label}을(를) 골라야 합니다.` })
      } else if (!columns.has(String(value))) {
        found.push({
          reason: `${param.label} '${String(value)}' 이(가) 아직 없습니다.`,
          fixedBy: makerOfColumn(String(value), catalog),
        })
      }
      continue
    }

    // `@youngs_modulus` 처럼 앞 단계의 값을 가리키는 칸.
    if (isReference(value)) {
      const key = String(value).slice(1)
      if (key.startsWith(FROM_SPECIMEN) || values.has(key)) continue
      found.push({
        reason: `${param.label}에 쓸 값이 아직 없습니다.`,
        fixedBy: makerOfValue(key, catalog),
      })
    }
  }
  return found
}

/** 그 열을 만드는 단계의 id. 옵션에 따라 이름이 달라지는 틀은 못 찾는다. */
function makerOfColumn(
  column: string,
  catalog: Map<string, ProcessingStep>
): string | undefined {
  for (const plugin of catalog.values()) {
    if (plugin.makes_columns.some((item) => item.key === column)) return plugin.id
  }
  return undefined
}

function makerOfValue(
  key: string,
  catalog: Map<string, ProcessingStep>
): string | undefined {
  for (const plugin of catalog.values()) {
    if (plugin.makes_values.some((item) => item.key === key)) return plugin.id
  }
  return undefined
}

/**
 * 이 단계를 **어디에 끼워야 하는가.** 권장 순서(`order`)를 지키는 자리.
 *
 * 사람이 순서도에서 고른 것을 끝에 붙이면, 탄성계수를 나중에 켰을 때 항복강도
 * 뒤로 가서 `@youngs_modulus` 가 안 풀린다. 순서는 이미 서버가 알고 있다.
 */
export function insertionIndex(
  steps: RecipeStep[],
  pluginId: string,
  catalog: Map<string, ProcessingStep>
): number {
  const order = catalog.get(pluginId)?.order ?? 100
  const at = steps.findIndex((step) => (catalog.get(step.plugin)?.order ?? 100) > order)
  return at === -1 ? steps.length : at
}

/** 순서도가 권장 순서와 어긋나 있는가. 사람이 손으로 옮겼을 수 있다. */
export function outOfOrder(
  steps: RecipeStep[],
  catalog: Map<string, ProcessingStep>
): boolean {
  const orders = steps.map((step) => catalog.get(step.plugin)?.order ?? 100)
  return orders.some((value, index) => index > 0 && value < orders[index - 1])
}

/**
 * 지금 구성에서 **쓸 수 있는 것 전부** — 원본 채널과, 각 단계가 만드는 열·값.
 *
 * 화면의 「변수 목록」이 이걸 그대로 보여 준다. `strain_true_plastic` 이 무엇인지
 * 코드를 읽어야 알게 두지 않는다.
 */
export interface Vocabulary {
  columns: (Produced & { madeBy?: string })[]
  values: (Produced & { madeBy: string })[]
}

export function vocabularyOf(
  steps: RecipeStep[],
  source: { key: string; label: string; si_unit: string }[],
  catalog: Map<string, ProcessingStep>
): Vocabulary {
  const columns: (Produced & { madeBy?: string })[] = source.map((item) => ({
    key: item.key,
    label: item.label,
    si_unit: item.si_unit,
    help: null,
  }))
  const values: (Produced & { madeBy: string })[] = []
  for (const step of steps) {
    const label = catalog.get(step.plugin)?.label ?? step.plugin
    for (const item of madeColumns(step, catalog)) columns.push({ ...item, madeBy: label })
    for (const item of catalog.get(step.plugin)?.makes_values ?? []) {
      values.push({ ...item, madeBy: label })
    }
  }
  return { columns, values }
}

/**
 * 순서도의 줄. **켠 단계는 도는 순서대로, 안 켠 것은 갈 자리에.**
 *
 * 순서도와 단계 목록이 따로 있으면 같은 목록이 두 칸에 있게 된다 — 가운데 칸만
 * 세로로 길어지고 곡선 쪽은 텅 빈다. 하나로 합치되, **켠 것은 실제로 도는
 * 순서**로 놓는다(사람이 손으로 옮겼을 수 있다). 안 켠 것은 켜면 들어갈 자리에
 * 끼워 둔다 — 그래야 "이걸 켜면 어디에 들어가는가" 가 보인다.
 */
export type FlowRow =
  | { kind: 'step'; step: RecipeStep; index: number; plugin?: ProcessingStep }
  | { kind: 'available'; plugin: ProcessingStep }

export function flowRows(
  steps: RecipeStep[],
  catalog: Map<string, ProcessingStep>,
  available: ProcessingStep[]
): FlowRow[] {
  const rows: FlowRow[] = steps.map((step, index) => ({
    kind: 'step',
    step,
    index,
    plugin: catalog.get(step.plugin),
  }))

  const used = new Set(steps.map((step) => step.plugin))
  for (const plugin of available) {
    if (used.has(plugin.id)) continue
    const at = insertionIndex(steps, plugin.id, catalog)
    // `at` 은 **단계 번호**다. 줄 목록에는 안 켠 줄도 섞여 있으므로 그 번호의
    // 단계 줄이 어디인지 다시 찾는다.
    const where = rows.findIndex((row) => row.kind === 'step' && row.index >= at)
    rows.splice(where === -1 ? rows.length : where, 0, { kind: 'available', plugin })
  }
  return rows
}

/** 요약에 몇 개까지. 넘으면 줄이 접혀 오히려 안 읽힌다. */
const SUMMARY_MAX = 3

/**
 * 접힌 줄에 보일 **설정 한 줄.**
 *
 * 접힌 줄이 이름만 갖고 있으면 "무엇으로 설정됐지" 를 확인하려고 **하나하나
 * 열어야 한다.** 그러면 접어 둔 뜻이 없다 — 접기는 세로 길이를 줄이려던 것이지
 * 정보를 숨기려던 것이 아니었다.
 *
 * 그래서 줄에 값을 적는다. **여는 것은 고칠 때만.**
 *
 * 지금 안 쓰이는 칸(`when` 조건이 안 맞는 것)은 뺀다 — 방법을 '최소제곱 회귀'
 * 로 두면 '직접 입력' 칸의 숫자는 아무 데도 안 쓰인다. 그것까지 적으면 요약이
 * 거짓말이 된다.
 */
export function stepSummary(
  step: RecipeStep,
  catalog: Map<string, ProcessingStep>,
  /** 바깥에서 들어오는 값. 있으면 참조를 사람이 읽는 이름으로 적는다. */
  inputs?: Map<string, ProcessingScalar>
): string {
  const plugin = catalog.get(step.plugin)
  if (!plugin) return ''

  const parts: string[] = []
  for (const param of plugin.params) {
    if (parts.length >= SUMMARY_MAX) {
      parts.push('…')
      break
    }
    if (!isUsed(param, step.options)) continue

    const value = step.options[param.name] ?? param.default
    if (value === null || value === undefined || value === '') continue

    if (isReference(value)) {
      parts.push(`${param.label} ${referenceLabel(String(value), inputs)}`)
      continue
    }
    if (param.role === 'column') {
      parts.push(String(value))
      continue
    }
    if (param.type === 'choice') {
      parts.push(param.choice_labels?.[String(value)] ?? String(value))
      continue
    }
    if (param.type === 'float' || param.type === 'int') {
      // **화면 단위로 적는다.** 저장은 SI 지만 사람은 0.05 m 를 50 mm 로 읽는다.
      const shown = display(param.unit, param.dimension)
      const number = toDisplay(Number(value), param.unit, param.dimension)
      const text = Number(number.toPrecision(4)).toString()
      parts.push(shown.unit ? `${param.label} ${text} ${shown.unit}` : `${param.label} ${text}`)
      continue
    }
    parts.push(`${param.label} ${String(value)}`)
  }
  return parts.join(' · ')
}
