/** 알림 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Notification = components['schemas']['NotificationOut']
export type NotificationRule = components['schemas']['NotificationRuleOut']
type UnreadCount = components['schemas']['UnreadCountOut']

export const notificationsApi = {
  list: () => api.get<Notification[]>('/notifications'),
  unreadCount: () => api.get<UnreadCount>('/notifications/unread-count'),
  read: (id: string) => api.post<Notification>(`/notifications/${id}/read`),
  readAll: () => api.post<UnreadCount>('/notifications/read-all'),
  /** 내가 받을 수 있는 알림과 켜짐 여부 — 역할이 정한 것만 온다. */
  rules: () => api.get<NotificationRule[]>('/notifications/rules'),
  setRule: (eventKind: string, enabled: boolean) =>
    api.patch<NotificationRule>(`/notifications/rules/${eventKind}`, { enabled }),
}
