/**
 * 외부 연동 API — 시스템 관리자만. **토큰은 보내기만 하고 받지 않는다.**
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Integration = components['schemas']['IntegrationOut']
export type IntegrationIn = components['schemas']['IntegrationIn']
export type IntegrationCheck = components['schemas']['IntegrationCheckOut']

export const integrationsApi = {
  list: () => api.get<Integration[]>('/integrations'),
  save: (system: string, body: IntegrationIn) =>
    api.put<Integration>(`/integrations/${encodeURIComponent(system)}`, body),
  check: (system: string) =>
    api.post<IntegrationCheck>(`/integrations/${encodeURIComponent(system)}/check`),
}
