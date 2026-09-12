/**
 * 계산식 API — **화면에서 적은 식이 적합식·처리 단계가 된다** (ADR 0030).
 *
 * 쓰기는 시스템 관리자만. 식은 모든 부서의 레시피·카드에 걸리는 것이라 부서
 * 설정이 아니다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Formula = components['schemas']['FormulaOut']
export type FormulaCreate = components['schemas']['FormulaCreate']
export type FormulaUpdate = components['schemas']['FormulaUpdate']
export type FormulaVariable = components['schemas']['FormulaVariableIn']
export type FormulaParameter = components['schemas']['FormulaParameterIn']
export type FormulaPreview = components['schemas']['FormulaPreviewOut']
export type FormulaVocabulary = components['schemas']['FormulaVocabularyOut']

export type FormulaKind = 'family' | 'scalar_step' | 'column_step'

/** 화면이 드는 모양 — 생성된 타입은 기본값 있는 칸을 선택으로 두는데, 편집기는 늘 든다. */
export type FormulaSpec = Omit<FormulaCreate, 'variables' | 'parameters' | 'applies_to'> & {
  variables: FormulaVariable[]
  parameters: FormulaParameter[]
  applies_to: string[]
}

/** 자리 셋 — 서버 `KIND_LABELS` 와 같다. 어디에 걸리는지를 함께 적는다. */
export const KINDS: { key: FormulaKind; label: string; where: string }[] = [
  { key: 'family', label: '적합식', where: '재료 상세 → 물성 카드 → 적합식 목록' },
  { key: 'scalar_step', label: '값 단계', where: '처리 레시피 → 단계 목록(값 하나를 낸다)' },
  { key: 'column_step', label: '열 단계', where: '처리 레시피 → 단계 목록(열 하나를 더한다)' },
]

export const formulasApi = {
  list: () => api.get<Formula[]>('/formulas'),
  vocabulary: () => api.get<FormulaVocabulary>('/formulas/vocabulary'),
  create: (payload: FormulaCreate) => api.post<Formula>('/formulas', payload),
  update: (id: string, payload: FormulaUpdate) => api.patch<Formula>(`/formulas/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/formulas/${id}`),
  preview: (spec: FormulaCreate, resultId: string) =>
    api.post<FormulaPreview>('/formulas/preview', { spec, result_id: resultId }),
}
