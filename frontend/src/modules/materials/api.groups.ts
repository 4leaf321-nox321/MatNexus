/**
 * 묶음 — **여러 시험을 묶어 만든 것**(ADR 0020).
 *
 * 무엇을 묶을 수 있는지는 **서버가 준다**(`/groups/kinds`). 화면이 목록을 적어
 * 두면 새 물성을 붙일 때 화면도 고쳐야 하고, 그러면 확장이 아니다.
 *
 * `materials/api.ts` 와 파일을 나눈 이유: 묶음은 재료의 하위 자원이 아니라
 * **재료·시험을 가로지르는 것**이다. 같은 파일에 두면 재료 API 가 점탄성을 알게
 * 된다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type GroupingSpec = components['schemas']['GroupingSpecOut']
export type GroupResult = components['schemas']['GroupResultOut']

export const groupsApi = {
  /** 고를 수 있는 묶음. `applies_to` 로 그 시험 종류의 것만. */
  kinds: (appliesTo?: string) =>
    api.get<GroupingSpec[]>(`/groups/kinds${appliesTo ? `?applies_to=${appliesTo}` : ''}`),

  ofMaterial: (materialId: string) =>
    api.get<GroupResult[]>(`/groups/materials/${materialId}`),

  create: (input: {
    plugin_id: string
    run_ids: string[]
    options?: Record<string, unknown>
    note?: string
  }) => api.post<GroupResult>('/groups', input),
}
