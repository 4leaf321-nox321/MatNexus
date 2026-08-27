/** 공지 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Notice = components['schemas']['NoticeOut']
type CreateRequest = components['schemas']['NoticeCreateRequest']
type UpdateRequest = components['schemas']['NoticeUpdateRequest']

export const noticesApi = {
  list: () => api.get<Notice[]>('/notices'),
  popup: () => api.get<Notice[]>('/notices/popup'),
  create: (payload: CreateRequest) => api.post<Notice>('/notices', payload),
  update: (id: string, payload: UpdateRequest) => api.patch<Notice>(`/notices/${id}`, payload),
  /** **「내리기」 와 다른 일이다.** 잘못 올린 것을 잠깐 감추려면 발행을 끄면
   *  되고(`update({ is_published: false })`) 그때 내용과 발행 시각은 남는다.
   *  이것은 그 공지가 있었다는 사실까지 없앤다. */
  remove: (id: string) => api.delete<void>(`/notices/${id}`),
  read: (id: string) => api.post<void>(`/notices/${id}/read`),
}
