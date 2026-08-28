/**
 * 장비 커넥터 — 장비 PC 가 보낸 파일이 시험이 되기 전까지의 자리.
 *
 * **판단은 서버가 한다.** 시편 후보도, 왜 후보가 없는지도, 다시 파싱할 수 있는지도
 * 서버가 실어 준다. 화면은 그것을 보여 주고 사람의 결정을 돌려보낸다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Connector = components['schemas']['ConnectorOut']
export type InboxItem = components['schemas']['InboxItemOut']
export type InboxItemDetail = components['schemas']['InboxItemDetail']
export type InboxPage = components['schemas']['Page_InboxItemOut_']
export type Candidate = components['schemas']['CandidateOut']
/** 붙일 시편을 찾을 때 받는 행. 시편 목록과 같은 모양이다. */
export type SpecimenChoice = components['schemas']['SpecimenRowOut']
type SpecimenChoicePage = components['schemas']['Page_SpecimenRowOut_']
/** 마법사에 붙여 넣을 부서. id 가 요점이다. */
export type WorkspaceRow = components['schemas']['WorkspaceOut']

/** 상태 순서. 표의 필터가 이 순서로 선다. */
export const INBOX_STATUSES = [
  'suggested',
  'needs_specimen',
  'failed',
  'received',
  'parsed',
  'registered',
  'discarded',
] as const
export type InboxStatus = (typeof INBOX_STATUSES)[number]

export const STATUS_LABELS: Record<InboxStatus, string> = {
  received: '대기',
  parsed: '읽는 중',
  suggested: '승인 대기',
  needs_specimen: '시편 필요',
  registered: '등록됨',
  failed: '실패',
  discarded: '버림',
}

export interface InboxQuery {
  status?: string
  connector_id?: string
  limit?: number
  offset?: number
}

function search(query: InboxQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export const pipelinesApi = {
  connectors: () => api.get<Connector[]>('/pipelines/connectors'),
  updateConnector: (
    id: string,
    body: { name?: string; is_active?: boolean; auto_register?: boolean }
  ) =>
    api.patch<Connector>(`/pipelines/connectors/${id}`, body),

  inbox: (query: InboxQuery = {}) => api.get<InboxPage>(`/pipelines/inbox${search(query)}`),
  item: (id: string) => api.get<InboxItemDetail>(`/pipelines/inbox/${id}`),
  assign: (id: string, body: { specimen_id: string; test_type?: string }) =>
    api.post<InboxItemDetail>(`/pipelines/inbox/${id}/assign`, body),
/** 승인 — 대기 중인 항목을 제 후보로 등록한다. */
  approve: (id: string) => api.post<InboxItemDetail>(`/pipelines/inbox/${id}/approve`, {}),
  /** 여럿을 한꺼번에. 막힌 것은 `failed`(id → 이유)로 온다 — 삼키지 않는다. */
  approveMany: (ids: string[]) =>
    api.post<{ approved: string[]; failed: Record<string, string> }>('/pipelines/inbox/approve', {
      ids,
    }),
  discard: (id: string, reason: string) =>
    api.post<void>(`/pipelines/inbox/${id}/discard`, { reason }),
  retry: (id: string) => api.post<InboxItem>(`/pipelines/inbox/${id}/retry`, {}),

  /**
   * 붙일 시편을 **재료를 거치지 않고** 찾는다. 시편 평면 목록(`/specimens`)을
   * 그대로 쓴다 — 모듈끼리 직접 부르지 않으므로 여기서 주소를 적는다.
   */
  /** 커넥터를 붙일 수 있는 부서 — 내가 속한 것. id 를 마법사에 넣는다. */
  workspaces: () => api.get<WorkspaceRow[]>('/workspaces'),

  findSpecimens: (q: string) =>
    api
      .get<SpecimenChoicePage>(`/specimens?q=${encodeURIComponent(q)}&limit=10`)
      .then((page) => page.items),
}
