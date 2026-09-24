/** 단추를 막을지 — 자료마다 붙어 오는 `access` 를 읽는 두 손잡이(ADR 0035). */

import type { EditAccess } from '@/modules/ownership/api'

/** 단추를 막을 때 붙일 말. 고칠 수 있으면 비어 있다. */
export function lockedTitle(access: EditAccess | null | undefined): string | undefined {
  return access && !access.can_edit ? (access.reason ?? '고칠 수 없습니다') : undefined
}

/** 고칠 수 있나 — **모르면 연다.** 서버가 막고 이유를 말한다. */
export function canEdit(access: EditAccess | null | undefined): boolean {
  return access?.can_edit ?? true
}
