/** VOC API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type VocItem = components['schemas']['VocOut']
type CreateRequest = components['schemas']['VocCreateRequest']

export const vocApi = {
  list: () => api.get<VocItem[]>('/voc'),
  create: (payload: CreateRequest) => api.post<VocItem>('/voc', payload),
  reply: (id: string, reply: string, status: string) =>
    api.post<VocItem>(`/voc/${id}/reply`, { reply, status }),
}
