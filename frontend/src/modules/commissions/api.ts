/** 측정 의뢰 API — 게시판이고 절차고, 끝이 데이터다. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Commission = components['schemas']['CommissionOut']
export type CommissionDetail = components['schemas']['CommissionDetailOut']
export type CommissionItem = components['schemas']['CommissionItemOut']
export type CommissionEvent = components['schemas']['CommissionEventOut']
export type CommissionPage = components['schemas']['Page_CommissionOut_']
export type CommissionStatus = components['schemas']['CommissionStatusOut']
export type LinkedRun = components['schemas']['LinkedRunOut']
export type CommissionItemIn = components['schemas']['CommissionItemIn']
export type CommissionCreate = components['schemas']['CommissionCreateRequest']
export type CommissionUpdate = components['schemas']['CommissionUpdateRequest']
type EventRequest = components['schemas']['CommissionEventRequest']

/**
 * 게시판 범위. `ours` — 우리 부서가 낸 것·받은 것(기본). `all` — 전사.
 *
 * 전에는 「전체」 가 곧 우리 부서 것이었다 — 보는 범위가 두 쪽뿐이었으니까. 보기를
 * 전원에게 연 뒤(ADR 0035 3단계) 「전체」 는 정말 전사가 됐고, 매일 보던 모양을
 * `ours` 로 이름 붙여 남겼다.
 */
export type Scope = 'ours' | 'mine' | 'received' | 'all'

export interface CommissionListParams {
  scope?: Scope
  status?: string
  q?: string
  limit?: number
  offset?: number
}

/**
 * 상태의 색. **차례와 이름은 서버가 준다**(`statuses` · `status_label`) — 여기는 색만.
 * 모르는 상태는 기본색이다.
 */
export const STATUS_TONES: Record<string, string> = {
  draft: 'border-border bg-muted text-muted-foreground',
  submitted:
    'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200',
  accepted:
    'border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-200',
  in_progress:
    'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200',
  on_hold:
    'border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-200',
  delivered:
    'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  closed: 'border-border bg-muted text-muted-foreground',
  rejected:
    'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200',
}

/** 항목이 「무엇으로 받을지」 의 특별한 값 — 카드가 아니라 곡선·처리 결과 그대로. */
export const DELIVERABLE_CURVES = 'curves'
export const DELIVERABLE_CURVES_LABEL = '곡선·처리 결과'

export const commissionsApi = {
  statuses: () => api.get<CommissionStatus[]>('/commissions/statuses'),
  list: (params: CommissionListParams = {}) => {
    const query = new URLSearchParams()
    if (params.scope) query.set('scope', params.scope)
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return api.get<CommissionPage>(`/commissions${suffix ? `?${suffix}` : ''}`)
  },
  get: (id: string) => api.get<CommissionDetail>(`/commissions/${id}`),
  create: (payload: CommissionCreate) => api.post<CommissionDetail>('/commissions', payload),
  /** 낸 사람이 작성 중·접수 대기일 때만. 서버가 같은 것을 막는다(`can_edit`). */
  update: (id: string, payload: CommissionUpdate) =>
    api.patch<CommissionDetail>(`/commissions/${id}`, payload),
  /** 작성 중인 것만 지운다. */
  remove: (id: string) => api.delete<void>(`/commissions/${id}`),
  /** 상태를 옮기거나(`status`) 말만 보탠다. 갈 수 있는 곳은 상세의 `allowed` 가 말한다. */
  event: (id: string, payload: EventRequest) =>
    api.post<CommissionDetail>(`/commissions/${id}/events`, payload),
  assign: (id: string, assigneeId: string | null) =>
    api.post<CommissionDetail>(`/commissions/${id}/assignee`, { assignee_id: assigneeId }),
  /** 시험을 항목에 붙인다 — 받는 쪽이 접수한 뒤(`can_link`). 같은 시료·같은 종류만. */
  linkRun: (id: string, itemId: string, runId: string) =>
    api.post<CommissionDetail>(`/commissions/${id}/items/${itemId}/runs`, { run_id: runId }),
  unlinkRun: (id: string, itemId: string, runId: string) =>
    api.delete<CommissionDetail>(`/commissions/${id}/items/${itemId}/runs/${runId}`),
  /** 새 재료 의뢰에 등록된 시료를 잇는다 — 받는 쪽이 재료·시료를 만든 뒤(`can_resolve`). */
  attachSample: (id: string, sampleId: string) =>
    api.post<CommissionDetail>(`/commissions/${id}/sample`, { sample_id: sampleId }),
  /** 종류 미정 항목에 시험 종류를 정한다 — 받는 쪽(`can_resolve`). */
  resolveItem: (id: string, itemId: string, testTypeKey: string) =>
    api.post<CommissionDetail>(`/commissions/${id}/items/${itemId}/test-type`, {
      test_type_key: testTypeKey,
    }),
}
