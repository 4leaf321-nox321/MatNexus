/** 누가 고치나 — 등록자와 편집을 받은 부서를 보고 넘긴다(ADR 0035). */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

/** 자료마다 붙어 오는 「지금 이 사람이 고칠 수 있나」. */
export type EditAccess = components['schemas']['EditAccessOut']
export type Ownership = components['schemas']['OwnershipOut']
export type OwnedKind = Ownership['kind']
export type OwnershipResult = components['schemas']['OwnershipChangeOut']
export type Person = components['schemas']['PersonOut']

/**
 * 넘길 것. **안 보낸 칸은 그대로다** — `edit_workspace_slug: null` 을 보내면 부여를 걷고,
 * 칸을 아예 안 보내면 손대지 않는다. 등록자만 넘기려다 부서 부여가 사라지면 안 된다.
 */
export interface OwnershipChange {
  registrant_id?: string
  edit_workspace_slug?: string | null
  include_children?: boolean
}

export const ownershipApi = {
  get: (kind: OwnedKind, id: string) => api.get<Ownership>(`/ownership/${kind}/${id}`),
  change: (kind: OwnedKind, id: string, body: OwnershipChange) =>
    api.put<OwnershipResult>(`/ownership/${kind}/${id}`, body),
  /** 넘겨받을 사람 — 이름과 대표 소속만 온다. */
  people: (q: string) =>
    api.get<Person[]>(`/ownership/people?q=${encodeURIComponent(q.trim())}`),
}
