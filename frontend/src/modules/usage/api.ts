/** 사용 현황 — 시스템 관리자만 본다. 숫자는 전부 서버가 센다(여기서 다시 셈하지 않는다). */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type UsageSummary = components['schemas']['UsageSummaryOut']
export type ViewedItem = components['schemas']['ViewedOut']

export const usageApi = {
  summary: (days: number) => api.get<UsageSummary>(`/usage/summary?days=${days}`),
}
