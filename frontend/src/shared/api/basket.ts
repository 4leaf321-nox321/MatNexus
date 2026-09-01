/**
 * 바구니 — **어느 화면에서든 담을 수 있어야 한다**(ADR 0024·0025).
 *
 * 워크벤치 모듈이 아니라 `shared` 에 있는 이유가 그것이다. 담는 단추는 시험 목록·
 * 재료 목록·카드 목록에 붙는데, 그 모듈들이 워크벤치 모듈을 부르면 **도메인이
 * 워크벤치를 알게 된다** — 방향이 뒤집히고, 그때부터 워크벤치를 떼어 낼 수 없다
 * (`boundaries.test.ts` 가 막는 그 방향이다).
 *
 * 바구니는 인증·알림처럼 **앱을 가로지르는 배관**이다. 이 파일은 아무 도메인 모듈도
 * import 하지 않는다 — `system.ts` 와 같은 자리다.
 *
 * ## 「지금 작업」 은 이 브라우저가 기억한다
 *
 * 어디에 담을지는 사람이 고른다. 그 선택은 **보는 방식**이라 브라우저에 둔다(정렬·
 * 접힘과 같다) — 담긴 것 자체는 서버에 있다. 다만 **단추가 이름을 늘 적는다**:
 * 어디에 담기는지 안 보이면 담고 나서 찾아야 한다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type BasketRun = components['schemas']['RunOut']
export type BasketRunDetail = components['schemas']['RunDetailOut']
export type BasketItem = components['schemas']['ItemOut']
export type ItemKind = 'test_run' | 'material' | 'card'

export const basketApi = {
  /** 내 부서의 작업들. **「이어서 하기」 가 이 목록이다.** */
  runs: (status?: 'running' | 'finished' | 'dropped') =>
    api.get<BasketRun[]>(`/workbench/runs${status ? `?status=${status}` : ''}`),

  run: (id: string) => api.get<BasketRunDetail>(`/workbench/runs/${id}`),

  create: (body: { workflow_key: string; title: string; note?: string }) =>
    api.post<BasketRunDetail>('/workbench/runs', body),

  /**
   * 이름·상태·진행을 고친다. **안 보낸 칸은 안 고친다** — 진행만 밀었는데 제목이
   * 지워지면 사람은 무엇이 지웠는지 모른다.
   */
  patch: (
    id: string,
    body: { title?: string; status?: string; steps?: Record<string, unknown>; note?: string }
  ) => api.patch<BasketRunDetail>(`/workbench/runs/${id}`, body),

  /** 담는다. **여럿을 한 번에** — 목록에서 골라 담는 일이라 한 건씩이면 왕복이 는다. */
  add: (id: string, kind: ItemKind, targetIds: string[], note?: string) =>
    api.post<BasketItem[]>(`/workbench/runs/${id}/items`, {
      kind,
      target_ids: targetIds,
      note,
    }),

  remove: (id: string, itemId: string) =>
    api.delete<void>(`/workbench/runs/${id}/items/${itemId}`),
}

/** 「지금 작업」 을 적어 두는 자리. 값은 작업 id 하나다. */
const ACTIVE = 'matnexus.basket.active'

export function activeRun(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE)
  } catch {
    // 저장소가 막힌 환경. 그때는 매번 고르면 된다.
    return null
  }
}

export function setActiveRun(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(ACTIVE, id)
    else window.localStorage.removeItem(ACTIVE)
  } catch {
    // 못 적어도 이번 방문 동안은 화면 상태로 이어진다.
  }
}
