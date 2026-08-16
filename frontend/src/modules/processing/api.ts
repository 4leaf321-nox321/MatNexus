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
export type ProcessingPreview = components['schemas']['ProcessingPreviewOut']
export type ProcessingResult = components['schemas']['ProcessingResultOut']
export type ProcessingStage = components['schemas']['ProcessingStageOut']
export type ProcessingScalar = components['schemas']['ProcessingScalarOut']
export type Recipe = components['schemas']['RecipeOut']
export type BatchOut = components['schemas']['BatchOut']
export type BatchItem = components['schemas']['BatchItemOut']
type RecipeSave = components['schemas']['RecipeSaveRequest']
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

/**
 * 어느 입력 칸이 무엇을 참조할 수 있는가. **칸마다 최대 하나다.**
 *
 * 처음에는 단위로 골랐다 — `param.unit === 'm'` 인 것을 전부 후보로 냈다.
 * 그랬더니 '게이지 길이' 칸에 게이지 길이·폭·두께 **셋이 붙었고**, 버튼 이름은
 * 전부 '참조' 라 무엇을 누르는지 알 수 없었다. 셋이 똑같아 보이는데 결과는
 * 다르다 — 잘못 누르면 게이지 길이 자리에 두께가 들어가고, 변형률이 조용히
 * 50배 틀린다.
 *
 * 단위가 같다고 뜻이 같은 것이 아니다. **이름으로 고른다.**
 */
export const REFERENCE_FOR: Record<string, { key: string; label: string }> = {
  gauge_length: { key: 'specimen_gauge_length', label: '시편의 게이지 길이' },
  area: { key: 'specimen_area', label: '시편의 단면적 (폭 곱하기 두께)' },
  youngs_modulus: { key: 'youngs_modulus', label: '앞 단계에서 잰 탄성계수' },
}

/** `@specimen_gauge_length` 같은 원문을 사람이 읽는 이름으로. */
export function referenceLabel(raw: string): string {
  const name = raw.startsWith(REFERENCE_PREFIX) ? raw.slice(1) : raw
  for (const item of Object.values(REFERENCE_FOR)) {
    if (item.key === name) return item.label
  }
  return name
}

const search = (params: Record<string, string | undefined>) => {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value)
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const processingApi = {
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

  updateRecipe: (key: string, payload: RecipeSave) =>
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
