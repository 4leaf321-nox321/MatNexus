/** 부서 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Workspace = components['schemas']['WorkspaceOut']
export type WorkspaceOption = components['schemas']['WorkspaceOption']
export type Member = components['schemas']['MemberOut']

export const workspacesApi = {
  /** 가입 화면용. 로그인 전에 부른다. */
  options: () => api.get<WorkspaceOption[]>('/workspaces/options'),

  list: (all = false) => api.get<Workspace[]>(all ? '/workspaces?all=true' : '/workspaces'),

  create: (slug: string, name: string) => api.post<Workspace>('/workspaces', { slug, name }),

  update: (slug: string, payload: { name?: string; is_active?: boolean }) =>
    api.patch<Workspace>(`/workspaces/${slug}`, payload),

  members: (slug: string) => api.get<Member[]>(`/workspaces/${slug}/members`),

  addMember: (slug: string, email: string, role: string) =>
    api.post<Member>(`/workspaces/${slug}/members`, { email, role }),

  setRole: (slug: string, userId: string, role: string) =>
    api.patch<Member>(`/workspaces/${slug}/members/${userId}`, { role }),

  removeMember: (slug: string, userId: string) =>
    api.delete<void>(`/workspaces/${slug}/members/${userId}`),
}
