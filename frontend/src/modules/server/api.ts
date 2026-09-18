/** 서버 현황 — 읽기 전용. 여기서 서버를 만지는 길은 없다. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type ServerInfo = components['schemas']['ServerInfoOut']
export type SemanticStatus = components['schemas']['SemanticStatusOut']
export type SemanticReindex = components['schemas']['SemanticReindexOut']
export type Disk = components['schemas']['DiskOut']
export type Queue = components['schemas']['QueueOut']
export type FailedJob = components['schemas']['FailedJobOut']

export const serverApi = {
  info: () => api.get<ServerInfo>('/server/info'),
  /** 큐 현황과 실패 목록. 도는 것은 문제없다 — 보이지 않는 것이 문제였다. */
  queue: () => api.get<Queue>('/server/queue'),
  /** 실패한 작업을 처음부터 다시. 워커가 다음 틱에 집어 간다. */
  retry: (jobId: string) => api.post<FailedJob>(`/server/queue/${jobId}/retry`),
  /** 의미 검색 현황 — 꺼졌으면 **왜, 그리고 무엇을 하면 되나**. */
  semantic: () => api.get<SemanticStatus>('/search/semantic'),
  /** 산문을 전부 다시 색인 — 워커가 뒤에서 돈다(202). */
  reindex: () => api.post<SemanticReindex>('/search/semantic/reindex'),
}
