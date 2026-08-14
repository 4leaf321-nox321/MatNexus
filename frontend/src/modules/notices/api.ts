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
  read: (id: string) => api.post<void>(`/notices/${id}/read`),
}
