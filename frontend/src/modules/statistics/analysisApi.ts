/**
 * 물성 분석 API — **다섯 화면이 같은 관측을 다르게 본다.**
 *
 * 서버가 채택된 결과(ADR 0007)만 세고, 안 채택된 것이 몇 건 빠졌는지 함께 준다.
 * 화면은 그 수를 반드시 보여 준다 — 조용히 빼면 n 이 왜 이 수인지 모른다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type AnalysisScalar = components['schemas']['AnalysisScalarOut']
export type Compare = components['schemas']['CompareOut']
export type AnalysisDistribution = components['schemas']['AnalysisDistributionOut']
export type SpecGap = components['schemas']['AnalysisSpecGapOut']
export type AnalysisTrend = components['schemas']['AnalysisTrendOut']
export type Coverage = components['schemas']['AnalysisCoverageOut']
export type Spread = components['schemas']['SpreadOut']
/** 비교에 더할 재료. 목록의 한 줄에서 이름만 쓴다. */
export type MaterialChoice = components['schemas']['MaterialOut']
type MaterialPage = components['schemas']['Page_MaterialOut_']

export const analysisApi = {
  /** 안 고르면 빈 표. 전체를 자동으로 세우면 94개짜리 표가 나온다. */
  compare: (materialIds: string[]) => {
    const query = materialIds.map((id) => `material_ids=${encodeURIComponent(id)}`).join('&')
    return api.get<Compare>(`/statistics/analysis/compare${query ? `?${query}` : ''}`)
  },

  distribution: (scalar: string, groupBy: string) =>
    api.get<AnalysisDistribution>(
      `/statistics/analysis/distribution?group_by=${groupBy}${
        scalar ? `&scalar=${encodeURIComponent(scalar)}` : ''
      }`
    ),

  specGap: () => api.get<SpecGap>('/statistics/analysis/spec-gap'),

  trend: (scalar: string, groupBy: string) =>
    api.get<AnalysisTrend>(
      `/statistics/analysis/trend?group_by=${groupBy}${
        scalar ? `&scalar=${encodeURIComponent(scalar)}` : ''
      }`
    ),

  coverage: () => api.get<Coverage>('/statistics/analysis/coverage'),

  /**
   * 비교에 더할 재료 찾기. **재료 모듈을 직접 부르지 않는다**(모듈 경계) —
   * 목록 주소를 여기서 안다. 두 글자 미만이면 서버에 안 묻는다.
   */
  findMaterials: (q: string) =>
    q.trim().length < 1
      ? Promise.resolve([] as MaterialChoice[])
      : api
          .get<MaterialPage>(`/materials?q=${encodeURIComponent(q.trim())}&limit=10`)
          .then((page) => page.items),
}
