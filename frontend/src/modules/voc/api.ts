/** VOC API — 게시판이고 절차다. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type VocItem = components['schemas']['VocOut']
export type VocDetail = components['schemas']['VocDetailOut']
export type VocEvent = components['schemas']['VocEventOut']
export type VocPage = components['schemas']['Page_VocOut_']
export type VocStatus = components['schemas']['VocStatusOut']
type CreateRequest = components['schemas']['VocCreateRequest']
type UpdateRequest = components['schemas']['VocUpdateRequest']
type EventRequest = components['schemas']['VocEventRequest']

export interface VocListParams {
  status?: string
  q?: string
  mine?: boolean
  limit?: number
  offset?: number
}

/**
 * 상태의 색. **차례와 이름은 서버가 준다**(`vocApi.statuses` · `status_label`) —
 * 여기는 색만 정한다. 모르는 상태는 기본색이다.
 */
export const STATUS_TONES: Record<string, string> = {
  open: 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200',
  accepted:
    'border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-200',
  in_progress:
    'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200',
  resolved:
    'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  closed: 'border-border bg-muted text-muted-foreground',
  rejected:
    'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200',
}

export const vocApi = {
  statuses: () => api.get<VocStatus[]>('/voc/statuses'),
  list: (params: VocListParams = {}) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    if (params.mine) query.set('mine', 'true')
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return api.get<VocPage>(`/voc${suffix ? `?${suffix}` : ''}`)
  },
  get: (id: string) => api.get<VocDetail>(`/voc/${id}`),
  create: (payload: CreateRequest) => api.post<VocDetail>('/voc', payload),
  /** 낸 사람은 남이 말을 남기기 전까지, 관리자는 언제나. 서버가 같은 것을 막는다
   *  (`MNX-VOC-0003`·`0004`) — 화면은 `can_edit` 를 보고 단추를 감출 뿐이다. */
  update: (id: string, payload: UpdateRequest) => api.patch<VocDetail>(`/voc/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/voc/${id}`),
  /** 상태를 옮기거나(`status`) 말만 보탠다(`status` 없이). 갈 수 있는 곳은 상세의
   *  `allowed` 가 말한다 — 화면이 규칙을 외우지 않는다. */
  event: (id: string, payload: EventRequest) => api.post<VocDetail>(`/voc/${id}/events`, payload),
}
