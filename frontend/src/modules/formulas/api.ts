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

/**
 * 자리 셋 — 서버 `KIND_LABELS` 와 같다. **무엇으로 무엇을 만드나**로 부른다. 「적합식·값
 * 단계·열 단계」 는 내부 구조의 이름이라 사용자가 못 알아들었다(2026-09-13). 화면이 이
 * 표로 첫 화면의 고르기 카드와 편집 창의 안내를 그린다.
 */
export const KINDS: {
  key: FormulaKind
  label: string
  /** 한 줄 용도. */
  purpose: string
  /** 어디에 뜨나 — 사람이 결과를 보러 갈 자리. */
  where: string
  /** 식에 쓰는 이름이 어디서 오나. */
  inputs: string
  /** 대표 예. 첫 창을 이것으로 채워 둔다 — 빈 칸보다 지워 쓰는 편이 빠르다. */
  example: string
}[] = [
  {
    key: 'family',
    label: '곡선에 맞추는 식',
    purpose: '곡선에 식을 맞춰 계수 산출 — 경화식·점도식처럼 카드에 담기는 식.',
    where: '재료 상세 › CAE 카드 › 탄소성(유변…) 카드의 식 후보',
    inputs: 'x = 곡선의 열(진소성변형률·전단율…). 계수(K, n …) = 데이터에서 산출.',
    example: 'K * pow(e0 + x, n)  — Swift 경화식',
  },
  {
    key: 'scalar_step',
    label: '값에서 값을 내는 식',
    purpose: '앞 단계의 값들로 새 값 하나 산출.',
    where: '처리 레시피의 단계 목록 — 레시피에 넣으면 결과에 값이 남는다',
    inputs: '처리 단계가 내는 값(항복강도·인장강도·탄성계수…) — 목록에서 선택.',
    example: 'proof_stress / tensile_strength  — 항복비',
  },
  {
    key: 'column_step',
    label: '곡선에서 열을 내는 식',
    purpose: '곡선의 열들로 새 열 하나 추가.',
    where: '처리 레시피의 단계 목록 — 결과 곡선에 열이 하나 는다',
    inputs: '원본 파일의 채널(변위·하중…)과 앞 단계가 만든 열(진응력…) — 목록에서 선택.',
    example: 'stress_true * 1e-6  — 진응력을 MPa 로',
  },
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
