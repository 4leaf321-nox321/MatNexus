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
export type Overview = components['schemas']['OverviewOut']
export type DivisionTally = components['schemas']['DivisionTallyOut']
export type DistributionReport = components['schemas']['DistributionReportOut']
export type DistributionCandidate = components['schemas']['DistributionCandidateOut']
export type DistributableKey = components['schemas']['DistributableKeyOut']

export const statisticsApi = {
  /**
   * 홈에 뿌리는 요약. **세는 일을 서버가 한다** — 재료 94개를 세려고 94행을
   * 받을 이유가 없다.
   */
  overview: () => api.get<Overview>('/statistics/overview'),

  /** 사업부별 현황 — 시험 수와, 그 시험이 걸친 재료·시료·시편 수. */
  divisions: () => api.get<DivisionTally[]>('/statistics/divisions'),

  forMaterial: (materialId: string, threshold?: number) =>
    api.get<MaterialStatistics>(
      `/statistics/materials/${materialId}${threshold ? `?threshold=${threshold}` : ''}`
    ),

  /** 이 묶음의 통계를 남긴다. 불변 — 다시 저장하면 새 행이 생긴다. */
  save: (body: { material_id: string; test_type_key: string; orientation: string }) =>
    api.post<EnsembleResult>('/statistics/ensembles', body),

  ensembles: (materialId: string) =>
    api.get<EnsembleResult[]>(`/statistics/ensembles?material_id=${materialId}`),

  /**
   * 분포를 물어볼 수 있는 항목. **값이 몇 개인지 함께 준다** — 화면이 미리
   * "이 항목은 5개뿐입니다" 를 말할 수 있어야 한다.
   */
  distributable: (materialId: string, testTypeKey: string, orientation: string) =>
    api.get<DistributableKey[]>(
      `/statistics/materials/${materialId}/distributable` +
        `?test_type_key=${encodeURIComponent(testTypeKey)}` +
        `&orientation=${encodeURIComponent(orientation)}`
    ),

  /**
   * 정규·로그정규·와이블을 나란히 맞춘다. **고르지 않고 견줘 준다.**
   *
   * `bootstrap` 을 낮추면 빨라지는 대신 p 값이 거칠어진다. 항목을 넘기며 훑을
   * 때 쓰라고 열어 뒀다 — 서버 기본값은 999 다.
   */
  distributions: (
    materialId: string,
    testTypeKey: string,
    orientation: string,
    scalarKey: string,
    bootstrap?: number
  ) =>
    api.get<DistributionReport>(
      `/statistics/materials/${materialId}/distributions` +
        `?test_type_key=${encodeURIComponent(testTypeKey)}` +
        `&orientation=${encodeURIComponent(orientation)}` +
        `&scalar_key=${encodeURIComponent(scalarKey)}` +
        (bootstrap === undefined ? '' : `&bootstrap=${bootstrap}`)
    ),
}
