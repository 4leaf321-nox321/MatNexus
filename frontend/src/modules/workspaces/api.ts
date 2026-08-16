/** 부서 API. */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Workspace = components['schemas']['WorkspaceOut']
export type WorkspaceOption = components['schemas']['WorkspaceOption']
export type Member = components['schemas']['MemberOut']
export type Reference = components['schemas']['WorkspaceReferenceOut']

export const workspacesApi = {
  /** 가입 화면용. 로그인 전에 부른다. */
  options: () => api.get<WorkspaceOption[]>('/workspaces/options'),

  list: (all = false) => api.get<Workspace[]>(all ? '/workspaces?all=true' : '/workspaces'),

  create: (slug: string, name: string, parentSlug?: string | null) =>
    api.post<Workspace>('/workspaces', { slug, name, parent_slug: parentSlug ?? null }),

  update: (slug: string, payload: { name?: string; is_active?: boolean }) =>
    api.patch<Workspace>(`/workspaces/${slug}`, payload),

  /** 상위 부서 바꾸기(조직 개편). `null` 이면 뿌리로 올린다.
   *
   *  이름 변경(PATCH)과 나눈 이유: 한 요청으로 받으면 "안 바꿈" 과 "뿌리로 올림"
   *  이 둘 다 `null` 이라 구분할 수 없다. */
  move: (slug: string, parentSlug: string | null, beforeSlug?: string | null) =>
    api.post<Workspace>(`/workspaces/${slug}/move`, {
      parent_slug: parentSlug,
      before_slug: beforeSlug ?? null,
    }),

  /** 무엇이 이 부서를 가리키는가. **삭제 버튼을 누르기 전에 보여 준다.** */
  references: (slug: string) => api.get<Reference[]>(`/workspaces/${slug}/references`),

  /** 막는 참조가 하나라도 있으면 서버가 거절한다. 보관이 여전히 기본 수단이다. */
  remove: (slug: string) => api.delete<void>(`/workspaces/${slug}`),

  /** 형제 사이 순서. 조직도 순서는 이름순도 생성순도 아니다 — 사람이 정한다. */
  reorder: (slug: string, direction: 'up' | 'down') =>
    api.post<Workspace>(`/workspaces/${slug}/reorder`, { direction }),

  members: (slug: string) => api.get<Member[]>(`/workspaces/${slug}/members`),

  addMember: (slug: string, email: string, role: string) =>
    api.post<Member>(`/workspaces/${slug}/members`, { email, role }),

  setRole: (slug: string, userId: string, role: string) =>
    api.patch<Member>(`/workspaces/${slug}/members/${userId}`, { role }),

  removeMember: (slug: string, userId: string) =>
    api.delete<void>(`/workspaces/${slug}/members/${userId}`),
}
