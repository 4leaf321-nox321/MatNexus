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
type SystemAdminRequest = components['schemas']['SystemAdminRequest']

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

  /** 대표 소속 — 이 사람이 로그인해서 처음 서는 부서.
   *
   *  멤버가 아닌 부서는 서버가 막는다. 멤버십을 만드는 것은 부서 멤버 화면의
   *  일이라, 여기서 겸하면 "대표 소속을 정했더니 없던 권한이 생겼다" 가 된다. */
  setHomeWorkspace: (id: string, workspaceSlug: string) =>
    api.post<Account>(`/accounts/${id}/home-workspace`, { workspace_slug: workspaceSlug }),

  /** 시스템 관리자 권한 — **주는 것과 빼는 것이 한 자리다.**
   *
   *  화면이 지금 값의 반대를 보낸다. 자기 계정과, 활성이 아닌 계정에 주는 것은
   *  서버가 막는다(마지막 관리자가 스스로 권한을 빼면 되돌릴 길이 없다). */
  setSystemAdmin: (id: string, grant: boolean) =>
    api.post<Account>(`/accounts/${id}/system-admin`, {
      is_system_admin: grant,
    } satisfies SystemAdminRequest),

  resetPassword: (id: string) => api.post<TemporaryPassword>(`/accounts/${id}/reset-password`),

  /** 삭제 전 미리보기 — 무엇이 딸려 있는지 보고 결정한다. */
  dependents: (id: string) => api.get<Reference[]>(`/accounts/${id}/dependents`),

  remove: (id: string, transferToId: string | null) =>
    api.delete<DeleteResult>(`/accounts/${id}`, { transfer_to_id: transferToId }),
}
