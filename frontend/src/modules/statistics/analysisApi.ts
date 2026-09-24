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
export type MaterialChoice = components['schemas']['MaterialChoiceOut']
export type CardItemSummary = components['schemas']['CardItemSummaryOut']
export type CardItemGroup = components['schemas']['CardItemGroupOut']
export type CardItemTally = components['schemas']['CardItemTallyOut']
export type CardItemRows = components['schemas']['CardItemRowsOut']
export type CardItemRow = components['schemas']['CardItemRowOut']
export type CardItemState = components['schemas']['CardItemStateOut']
export type CardItemColumn = components['schemas']['CardItemColumnOut']
export type CardItemCell = components['schemas']['CardItemCellOut']
export type CardItemValue = components['schemas']['CardItemValueOut']

/** 전체(재료 줄)를 거르는 조건. 비운 것은 안 보낸다. */
export interface CardItemQuery {
  q?: string | null
  family?: string | null
  category?: string | null
  item?: string | null
  withSources?: boolean
  limit: number
  offset: number
}

export const analysisApi = {
  /** 안 고르면 빈 표. 전체를 자동으로 세우면 94개짜리 표가 나온다. */
  compare: (materialIds: string[]) => {
    const query = materialIds.map((id) => `material_ids=${encodeURIComponent(id)}`).join('&')
    return api.get<Compare>(`/statistics/analysis/compare${query ? `?${query}` : ''}`)
  },

  /** 항목을 여럿 주면 **열이 여럿**이 된다. 안 주면 서버가 가장 많은 하나를 고른다. */
  distribution: (scalars: string[], groupBy: string) =>
    api.get<AnalysisDistribution>(
      `/statistics/analysis/distribution?group_by=${groupBy}${scalars
        .map((one) => `&scalar=${encodeURIComponent(one)}`)
        .join('')}`
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
   * 카드 항목 **요약** — 재료군·분류 x 항목란. 줄이 분류라 재료 수와 무관하게 작다.
   * 칸의 상태는 서버가 정한다(요약 · 전체 · 칸이 같은 판정).
   */
  cardItemSummary: () => api.get<CardItemSummary>('/statistics/analysis/card-items'),

  /** 카드 항목 **전체** — 재료 줄. 거르고 자르는 것은 서버다(한 번에 200줄까지). */
  cardItemRows: (query: CardItemQuery) => {
    const params = new URLSearchParams()
    for (const [key, value] of [
      ['q', query.q],
      ['family', query.family],
      ['category', query.category],
      ['item', query.item],
    ] as const) {
      if (value) params.set(key, value)
    }
    if (query.withSources) params.set('with_sources', 'true')
    params.set('limit', String(query.limit))
    params.set('offset', String(query.offset))
    return api.get<CardItemRows>(`/statistics/analysis/card-items/materials?${params}`)
  },

  /** 칸 하나의 속 — 카드마다 든 값 · 시험 · 선언. **누를 때만** 받는다. */
  cardItemCell: (materialId: string, item: string) =>
    api.get<CardItemCell>(
      `/statistics/analysis/card-items/cell?material_id=${encodeURIComponent(
        materialId
      )}&item=${encodeURIComponent(item)}`
    ),

  /**
   * 비교에 담을 수 있는 재료 — **채택된 물성이 있는 것만.** 전체 목록에서 고르게
   * 하면 물성이 없는 재료를 담고 빈 줄을 본다.
   */
  materials: () => api.get<MaterialChoice[]>('/statistics/analysis/materials'),
}
