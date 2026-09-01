/**
 * 워크벤치 API — 작업과 바구니(ADR 0025).
 *
 * **서버는 담아 두기만 한다.** 단계가 무엇이고 무엇으로 완료를 판정하는지는 화면이
 * 안다 — `steps` 는 자유 모양으로 오간다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type WorkbenchRun = components['schemas']['RunOut']
export type WorkbenchRunDetail = components['schemas']['RunDetailOut']
export type WorkbenchItem = components['schemas']['ItemOut']
export type ItemKind = 'test_run' | 'material' | 'card'

export const workbenchApi = {
  /** 내 부서의 작업들. **「이어서 하기」 가 이 목록이다.** */
  runs: (status?: 'running' | 'finished' | 'dropped') =>
    api.get<WorkbenchRun[]>(`/workbench/runs${status ? `?status=${status}` : ''}`),

  run: (id: string) => api.get<WorkbenchRunDetail>(`/workbench/runs/${id}`),

  create: (body: { workflow_key: string; title: string; note?: string }) =>
    api.post<WorkbenchRunDetail>('/workbench/runs', body),

  /**
   * 이름·상태·진행을 고친다. **안 보낸 칸은 안 고친다** — 진행만 밀었는데 제목이
   * 지워지면 사람은 무엇이 지웠는지 모른다.
   */
  patch: (
    id: string,
    body: { title?: string; status?: string; steps?: Record<string, unknown>; note?: string }
  ) => api.patch<WorkbenchRunDetail>(`/workbench/runs/${id}`, body),

  /** 담는다. **여럿을 한 번에** — 목록에서 골라 담는 일이라 한 건씩이면 왕복이 는다. */
  add: (id: string, kind: ItemKind, targetIds: string[], note?: string) =>
    api.post<WorkbenchItem[]>(`/workbench/runs/${id}/items`, {
      kind,
      target_ids: targetIds,
      note,
    }),

  remove: (id: string, itemId: string) =>
    api.delete<void>(`/workbench/runs/${id}/items/${itemId}`),
}
