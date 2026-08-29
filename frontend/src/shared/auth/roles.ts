/**
 * 이 사람이 무엇을 할 수 있나 — **한 곳에서 판정한다.**
 *
 * 사이드바에만 있던 규칙이다(`memberships.some(role === 'manager')`). 화면들이
 * 쓰기 단추를 가리기 시작하면서 같은 식이 여러 곳에 복사될 참이라 여기로 모은다 —
 * 갈라지면 **어떤 화면은 단추를 보이고 어떤 화면은 안 보이는** 상태가 되고, 그
 * 차이를 아무도 설명할 수 없다.
 *
 * **이것은 표시일 뿐 권한이 아니다.** 권한은 서버가 판정한다 — 여기를 고쳐
 * 우회할 수 있으면 그건 애초에 보안이 아니다. 여기서 하는 일은 하나다:
 * **눌러 보고 403 을 알게 하지 않는 것.**
 */

import type { CurrentUser } from '@/shared/auth/AuthContext'

export function isSystemAdmin(user: CurrentUser | null | undefined): boolean {
  return Boolean(user?.is_system_admin)
}

/** 어느 부서에서든 관리자인가. 시스템 관리자는 언제나 참이다. */
export function isAnyManager(user: CurrentUser | null | undefined): boolean {
  return isSystemAdmin(user) || (user?.memberships ?? []).some((one) => one.role === 'manager')
}
