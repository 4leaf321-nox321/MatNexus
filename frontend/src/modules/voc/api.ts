/** VOC API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type VocItem = components['schemas']['VocOut']
type CreateRequest = components['schemas']['VocCreateRequest']
type UpdateRequest = components['schemas']['VocUpdateRequest']

export const vocApi = {
  list: () => api.get<VocItem[]>('/voc'),
  create: (payload: CreateRequest) => api.post<VocItem>('/voc', payload),
  /** 낸 사람은 답변 전까지, 관리자는 언제나. 서버가 같은 것을 막는다
   *  (`MNX-VOC-0003`·`0004`) — 화면은 단추를 안 보이게 할 뿐이다. */
  update: (id: string, payload: UpdateRequest) => api.patch<VocItem>(`/voc/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/voc/${id}`),

  reply: (id: string, reply: string, status: string) =>
    api.post<VocItem>(`/voc/${id}/reply`, { reply, status }),
}
