/**
 * 통계 API — 재료 단위 물성.
 *
 * **조회는 늘 최신을 계산한다.** 시험이 하나 더 붙으면 평균이 달라지는 것이
 * 맞고, 화면은 그것을 보여 줘야 한다. 남겨야 할 때만 `ensembles` 로 저장한다 —
 * 그때의 표본과 값이 통째로 박힌다(ADR 0007 과 같은 모델).
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type MaterialStatistics = components['schemas']['MaterialStatisticsOut']
export type StatisticsGroup = components['schemas']['GroupOut']
export type ScalarStats = components['schemas']['ScalarStatsOut']
export type CurveStats = components['schemas']['CurveStatsOut']
export type Outlier = components['schemas']['OutlierOut']
export type EnsembleResult = components['schemas']['EnsembleResultOut']

export const statisticsApi = {
  forMaterial: (materialId: string, threshold?: number) =>
    api.get<MaterialStatistics>(
      `/statistics/materials/${materialId}${threshold ? `?threshold=${threshold}` : ''}`
    ),

  /** 이 묶음의 통계를 남긴다. 불변 — 다시 저장하면 새 행이 생긴다. */
  save: (body: { material_id: string; test_type_key: string; orientation: string }) =>
    api.post<EnsembleResult>('/statistics/ensembles', body),

  ensembles: (materialId: string) =>
    api.get<EnsembleResult[]>(`/statistics/ensembles?material_id=${materialId}`),
}
