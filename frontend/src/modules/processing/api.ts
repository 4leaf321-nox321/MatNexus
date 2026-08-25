/**
 * 처리 API — 단계 목록, 미리보기, 결과, 레시피.
 *
 * **모듈을 따로 둔 이유.** 처리는 시험 등록과 성격이 다르다. 시험은 "파일을
 * 받아 곡선으로 만드는" 일이고, 처리는 "그 곡선을 물성이 쓸 수 있게 바꾸는"
 * 일이다. 백엔드도 `app/modules/tests/processing.py` 로 나눠 두었고, 모듈
 * 이름은 백엔드와 프론트가 같아야 한다(CLAUDE.md).
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type ProcessingStep = components['schemas']['ProcessingStepOut']
export type StepParam = components['schemas']['StepParamOut']
/**
 * 계산이 만들어 내는 것 하나 — 열이거나 값이다. 이름·뜻·저장 단위를 같이 갖는다.
 *
 * `strain_true_plastic` 만 보여 주면 그게 무엇인지 코드를 읽어야 알게 되고,
 * 그러면 아무도 안 읽는다.
 */
export type Produced = components['schemas']['ProducedOut']
export type ProcessingPreview = components['schemas']['ProcessingPreviewOut']
export type ProcessingResult = components['schemas']['ProcessingResultOut']
export type ResultCurve = components['schemas']['ResultCurveOut']
export type ProcessingStage = components['schemas']['ProcessingStageOut']
export type ProcessingScalar = components['schemas']['ProcessingScalarOut']
export type Recipe = components['schemas']['RecipeOut']
export type BatchOut = components['schemas']['BatchOut']
export type BatchItem = components['schemas']['BatchItemOut']
type RecipeUpdate = components['schemas']['RecipeUpdateRequest']
type RecipeCreate = components['schemas']['RecipeCreateRequest']

/** 레시피의 한 줄. 서버는 `dict` 로 받으므로 생성 타입이 안 나온다. */
export interface RecipeStep {
  plugin: string
  options: Record<string, unknown>
}

/**
 * 앞 단계가 낸 값을 가리키는 표기.
 *
 * 사람이 탄성계수를 손으로 옮겨 적으면, 방법을 바꿔 다시 쟀을 때 항복강도만
 * 옛 값으로 남는다 — 그 결과는 그럴듯해 보인다. 시편 치수도 같은 표기를 쓴다.
 */
export const REFERENCE_PREFIX = '@'

export const isReference = (value: unknown): value is string =>
  typeof value === 'string' && value.startsWith(REFERENCE_PREFIX)

/** 시편에서 온 값의 키 앞머리. `게이지 길이` 칸 ↔ `specimen_gauge_length`. */
export const FROM_SPECIMEN = 'specimen_'

/**
 * 이 입력 칸에 이어 붙일 값. **없으면 `null`.**
 *
 * ## 왜 이름으로 찾는가
 *
 * 처음에는 **단위**로 골랐다 — `unit === 'm'` 인 것을 전부 후보로 냈다. 그랬더니
 * '게이지 길이' 칸에 게이지 길이·폭·두께 **셋이 붙었고**, 버튼 이름은 전부
 * '참조' 라 무엇을 누르는지 알 수 없었다. 잘못 누르면 게이지 길이 자리에 두께가
 * 들어가고 **변형률이 조용히 50배 틀린다.**
 *
 * 그래서 이름 셋을 화면에 박았다. 이번엔 반대 문제가 났다 — 규격에 칸을 더해도
 * (자유 길이·직경) 처리 화면이 모른다. 값은 이미 서버가 보내고 있는데 집을
 * 자리가 없어서, 사람은 자를 대고 다시 잰다.
 *
 * 입력 칸 이름과 시편 치수 이름은 **원래 같은 이름 공간**이다. 그러니 목록을
 * 들고 있을 필요가 없다 — 이름이 맞는 것 하나를 찾으면 된다. 단위로 고르는 것도
 * 아니고 표를 박는 것도 아니다.
 *
 * ## 이름이 다를 때는 칸이 말해 준다
 *
 * 이름이 늘 같지는 않다. 네킹을 자르는 `manual_index` 칸은 앞 단계가 낸
 * `necking_candidate_index` 를 받는데, **이름이 달라서 단추가 안 떴다** —
 * 사람이 후보 index 를 눈으로 보고 손으로 옮겨 적어야 했고, 곡선을 다시
 * 처리하면 옛 index 가 남는다.
 *
 * 그래서 칸이 `links_to` 로 가리킨다. **화면이 짝을 외우지 않는다** — 새
 * 계산이 그런 칸을 만들어도 여기는 안 고친다(D7).
 */
export function referenceFor(
  param: Pick<StepParam, 'name' | 'links_to'>,
  available: Map<string, ProcessingScalar>
): ProcessingScalar | null {
  const wanted = param.links_to ?? param.name
  return available.get(`${FROM_SPECIMEN}${wanted}`) ?? available.get(wanted) ?? null
}

/**
 * 이 칸에 이어 붙일 수 있는 값들. **이름이 맞는 것이 맨 앞이다.**
 *
 * ## 왜 여럿을 내는가 — 한 번 되돌렸던 자리다
 *
 * 처음에는 **단위만** 보고 후보를 냈다. '게이지 길이' 칸에 게이지 길이·폭·두께
 * 셋이 붙었고 버튼 이름이 전부 '참조' 라, 잘못 누르면 **변형률이 조용히 50배
 * 틀렸다.** 그래서 이름이 맞는 하나로 좁혔다.
 *
 * 그런데 그러면 **고를 수가 없다.** 같은 뜻의 값이 여럿일 때(시편 실측과 규격
 * 공칭처럼) 화면이 하나를 골라 버리고, 사람은 다른 것을 쓸 길이 없다.
 *
 * 지금은 여럿을 내되 **그때 실패한 두 가지를 고쳤다.**
 *
 *   이름이 맞는 것이 맨 앞이다   무엇이 권장인지 순서로 말한다
 *   줄마다 이름과 지금 값을 적는다  '참조' 셋이 아니라 「폭 · 12.5 mm」다
 *
 * 후보가 하나뿐이면 화면은 지금처럼 단추 하나만 낸다 — 고를 것이 없는데 목록을
 * 내면 누르는 수만 는다.
 */
export function referencesFor(
  param: Pick<StepParam, 'name' | 'links_to' | 'unit' | 'dimension'>,
  available: Map<string, ProcessingScalar>
): ProcessingScalar[] {
  const best = referenceFor(param, available)
  if (!param.unit) return best ? [best] : []
  // **뜻이 같은 것만 후보다.** 단위가 다르면 애초에 그 자리에 못 들어간다.
  const alike = [...available.values()].filter(
    (one) =>
      one.key !== best?.key &&
      one.si_unit === param.unit &&
      (param.dimension ?? one.dimension ?? null) === (one.dimension ?? null)
  )
  return best ? [best, ...alike] : alike
}

/** `@specimen_gauge_length` 같은 원문을 사람이 읽는 이름으로. */
export function referenceLabel(raw: string, available?: Map<string, ProcessingScalar>): string {
  const name = raw.startsWith(REFERENCE_PREFIX) ? raw.slice(1) : raw
  const known = available?.get(name)
  if (known) return known.label
  return name
}

const search = (params: Record<string, string | undefined>) => {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value)
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const processingApi = {
  /**
   * 이 시험을 돌리면 **바깥에서 들어오는 값**. 시편 치수와 단면적이다.
   *
   * 돌려 보기 전에 알아야 한다 — 이어 붙인 값이 몇인지 보여 주고, 그 자리에서
   * 고칠 수 있게 하려면 화면이 숫자를 갖고 있어야 한다.
   */
  inputs: (testRunId: string) =>
    api.get<ProcessingScalar[]>(`/processing/inputs?test_run_id=${testRunId}`),

  /** 등록된 단계와 입력 칸. **화면이 이 응답만으로 폼을 그린다.** */
  steps: (testType?: string) =>
    api.get<ProcessingStep[]>(`/processing/steps${search({ test_type: testType })}`),

  /** 저장하지 않고 돌려 본다. */
  preview: (
    body: { test_run_id: string; source_curve_key?: string | null; steps: RecipeStep[] },
    axes?: { x?: string; y?: string }
  ) =>
    api.post<ProcessingPreview>(
      `/processing/preview${search({ x: axes?.x, y: axes?.y })}`,
      body
    ),

  /** 결과를 저장한다. 불변 — 다시 돌리면 새 행이 생긴다. */
  save: (body: {
    test_run_id: string
    source_curve_key?: string | null
    steps: RecipeStep[]
    recipe_key?: string | null
  }) => api.post<ProcessingResult>('/processing/results', body),

  results: (testRunId: string) =>
    api.get<ProcessingResult[]>(`/processing/results?test_run_id=${testRunId}`),

  /**
   * 저장된 결과의 곡선. **다시 계산하지 않는다** — 저장할 때 쓴 파일을 읽는다.
   *
   * 축을 주지 않으면 서버가 고른다(공칭 먼저, 없으면 진응력). 어떤 축을 고를 수
   * 있는지가 곧 레시피가 만든 열이다 — 진응력 단계를 안 넣었으면 그 축이 목록에
   * 아예 없고, 그 없음이 "왜 진응력 곡선이 안 보이나" 의 답이다.
   */
  curve: (resultId: string, axes?: { x?: string; y?: string }) =>
    api.get<ResultCurve>(
      `/processing/results/${resultId}/curve${search({ x: axes?.x, y: axes?.y })}`
    ),

  /** **이 시험의 물성은 이것.** 시험당 하나뿐이다(ADR 0007). */
  adopt: (resultId: string) =>
    api.post<ProcessingResult>(`/processing/results/${resultId}/adopt`, {}),

  /** 채택만 거둔다 — 결과는 지워지지 않는다. */
  unadopt: (resultId: string) => api.delete<void>(`/processing/results/${resultId}/adopt`),

  /** 여러 시험에 같은 단계를. **부분 실패를 건별로 돌려준다.** */
  batch: (body: {
    test_run_ids: string[]
    source_curve_key?: string | null
    steps: RecipeStep[]
    recipe_key?: string | null
    adopt: boolean
  }) => api.post<BatchOut>('/processing/batch', body),

  recipes: (testType?: string) =>
    api.get<Recipe[]>(`/processing/recipes${search({ test_type: testType })}`),

  createRecipe: (payload: RecipeCreate) => api.post<Recipe>('/processing/recipes', payload),

  /** 단계를 통째로 갈아 끼운다. `expected_revision` 필수 — ADR 0015. */
  updateRecipe: (key: string, payload: RecipeUpdate) =>
    api.put<Recipe>(`/processing/recipes/${key}`, payload),

  removeRecipe: (key: string) => api.delete<void>(`/processing/recipes/${key}`),
}

/**
 * 지금 설정에서 이 칸이 쓰이는가.
 *
 * 조건은 서버가 `ParamSpec.when` 으로 준다 — 어느 방법이 어느 칸을 쓰는지는
 * **계산의 성질**이지 화면의 사정이 아니다. 화면에 적으면 계산을 고칠 때 두
 * 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
 */
export function isUsed(
  param: { when?: Record<string, string[]> | null },
  options: Record<string, unknown>
): boolean {
  return Object.entries(param.when ?? {}).every(([key, allowed]) =>
    allowed.includes(String(options[key]))
  )
}
