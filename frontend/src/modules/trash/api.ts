/**
 * 휴지통 — 지운 것을 보고, 되살리고, 영영 지운다.
 *
 * **판단은 서버가 한다.** 되살릴 수 있는지(`blocked`)도, 아래에 무엇이 딸렸는지
 * (`below`)도 서버가 실어 준다. 화면이 스스로 세면 사람이 본 숫자와 실제로
 * 손대는 것이 어긋나고, 그때 사람이 누른 「예」 는 다른 것에 대한 대답이 된다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type TrashItem = components['schemas']['TrashItemOut']
export type TrashDone = components['schemas']['TrashDoneOut']

/** 종류 순서. 표의 필터가 이 순서로 선다 — 위에서 아래로 계층이다. */
export const TRASH_KINDS = ['material', 'sample', 'specimen', 'test_run'] as const
export type TrashKind = (typeof TRASH_KINDS)[number]

export const trashApi = {
  list: (params: { kind?: string; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.kind) query.set('kind', params.kind)
    if (params.limit) query.set('limit', String(params.limit))
    const suffix = query.toString()
    return api.get<TrashItem[]>(`/trash${suffix ? `?${suffix}` : ''}`)
  },

  restore: (kind: string, id: string) =>
    api.post<TrashDone>(`/trash/${kind}/${id}/restore`, {}),

  /**
   * 영영 지운다. **`confirm` 을 서버가 다시 받는다** — 창에서 물었더라도,
   * 이 길은 API 로도 열려 있어서 실수로 부르면 데이터가 안 돌아온다.
   */
  purge: (kind: string, id: string) =>
    api.delete<TrashDone>(`/trash/${kind}/${id}?confirm=true`),
}
