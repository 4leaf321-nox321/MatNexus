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

/**
 * 전사로 자료를 고치는 사람인가 — 시스템 관리자와 자료 관리자(ADR 0035).
 * 검토의 뜻이 있는 일의 단추가 이것으로 정해진다 — 카드 확정 · 새 기준정보 값 ·
 * 핸드북 승인 · 부서 없이 올리는 정의.
 */
export function isDataSteward(user: CurrentUser | null | undefined): boolean {
  return isSystemAdmin(user) || Boolean(user?.is_data_manager)
}

/**
 * 어느 부서에서든 관리자인가. 시스템 관리자는 언제나 참이다.
 *
 * **고칠 권한의 근거로 쓰지 않는다**(ADR 0035 3단계). 부서 관리자가 하는 일은 멤버 ·
 * 장비 커넥터와 수신함 · 의뢰 알림뿐이다 — 그것도 커넥터는 줄마다 서버가 `can_manage`
 * 로 말한다(「어느 부서든」 이 아니라 **그 커넥터의 부서**). 여기는 사이드바의 「내 부서」
 * 묶음을 보일지만 정한다.
 */
export function isAnyManager(user: CurrentUser | null | undefined): boolean {
  return isSystemAdmin(user) || (user?.memberships ?? []).some((one) => one.role === 'manager')
}
