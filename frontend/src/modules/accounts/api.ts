/**
 * 계정 API.
 *
 * 타입은 백엔드 스키마에서 생성한 것을 쓴다 — 손으로 적지 않는다(D13).
 * 모듈별 api.ts 를 두는 이유: 화면이 엔드포인트 경로를 직접 알면, 경로가 바뀔 때
 * 화면을 훑어야 한다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Account = components['schemas']['AccountOut']
export type AccountStatus = 'pending' | 'active' | 'suspended'
export type Reference = components['schemas']['ReferenceOut']
type DeleteResult = components['schemas']['DeleteAccountResponse']
type TemporaryPassword = components['schemas']['TemporaryPasswordResponse']
type SignupRequest = components['schemas']['SignupRequest']
type CreateAccountRequest = components['schemas']['CreateAccountRequest']

export const accountsApi = {
  signup: (payload: SignupRequest) => api.post<Account>('/accounts/signup', payload),

  list: (status?: AccountStatus) =>
    api.get<Account[]>(status ? `/accounts?status=${status}` : '/accounts'),

  create: (payload: CreateAccountRequest) =>
    api.post<TemporaryPassword>('/accounts', payload),

  approve: (id: string, workspaceSlug: string | null, role: string) =>
    api.post<Account>(`/accounts/${id}/approve`, {
      workspace_slug: workspaceSlug,
      role,
    }),

  reject: (id: string, note: string) => api.post<Account>(`/accounts/${id}/reject`, { note }),

  suspend: (id: string) => api.post<Account>(`/accounts/${id}/suspend`),
  activate: (id: string) => api.post<Account>(`/accounts/${id}/activate`),

  resetPassword: (id: string) => api.post<TemporaryPassword>(`/accounts/${id}/reset-password`),

  /** 삭제 전 미리보기 — 무엇이 딸려 있는지 보고 결정한다. */
  dependents: (id: string) => api.get<Reference[]>(`/accounts/${id}/dependents`),

  remove: (id: string, transferToId: string | null) =>
    api.delete<DeleteResult>(`/accounts/${id}`, { transfer_to_id: transferToId }),
}
