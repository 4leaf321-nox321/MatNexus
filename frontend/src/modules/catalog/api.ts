/**
 * 물성 카탈로그 — 문헌·데이터시트에서 채굴된 물성값의 보관소 (ADR 0027).
 *
 * **읽기 전용이다.** 데이터는 서버의 이관 스크립트로만 들어오고, 화면은 보고
 * 고르기만 한다. 값마다 출처와 품질 등급(tier 1~4)이 붙어 있다 — **4는 근거
 * 없는 값**(계산·추정·가정)이라 화면이 반드시 구별해 보여 준다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type CatalogSummary = components['schemas']['CatalogSummaryOut']
export type CatalogMaterial = components['schemas']['CatalogMaterialOut']
export type CatalogMaterialPage = components['schemas']['CatalogMaterialPage']
export type CatalogMaterialDetail = components['schemas']['CatalogMaterialDetailOut']
export type CatalogValue = components['schemas']['CatalogValueOut']

/** 품질 등급 라벨 — 서버 독트린 그대로. 4는 신뢰 경로에서 빠진다. */
export const TIER_LABELS: Record<number, string> = {
  1: '실측',
  2: '핸드북',
  3: '2차 인용',
  4: '추정',
}

export const catalogApi = {
  summary: () => api.get<CatalogSummary>('/catalog/summary'),
  materials: (params: {
    q?: string
    subsystem?: string
    category?: string
    limit?: number
    offset?: number
  }) => {
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) search.set(key, String(value))
    }
    const suffix = search.toString()
    return api.get<CatalogMaterialPage>(`/catalog/materials${suffix ? `?${suffix}` : ''}`)
  },
  material: (id: string) => api.get<CatalogMaterialDetail>(`/catalog/materials/${id}`),
}
