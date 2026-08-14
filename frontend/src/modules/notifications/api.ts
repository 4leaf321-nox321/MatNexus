/** 알림 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Notification = components['schemas']['NotificationOut']
type UnreadCount = components['schemas']['UnreadCountOut']

export const notificationsApi = {
  list: () => api.get<Notification[]>('/notifications'),
  unreadCount: () => api.get<UnreadCount>('/notifications/unread-count'),
  read: (id: string) => api.post<Notification>(`/notifications/${id}/read`),
  readAll: () => api.post<UnreadCount>('/notifications/read-all'),
}
