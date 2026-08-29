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
/**
 * 거를 수 있는 종류 — **두 묶음이다.**
 *
 * 위는 재료 계층과 시험이라 **아래로 딸린 것이 있다**(재료를 되살리면 그 아래가
 * 함께 돌아온다). 아래는 데이터 수집 체계라 정의 한 줄이 통째로 하나다. 성격이
 * 다르므로 고르는 자리에서도 갈라 세운다.
 *
 * **라벨을 여기 적어 둔다.** 서버가 주는 `kind_label` 이 정본이지만, 그 종류로
 * 지운 것이 하나도 없으면 목록에 행이 없어서 라벨을 알 수 없다 — 그때 드롭다운에
 * `test_type` 같은 날 키가 뜬다.
 */
export const TRASH_GROUPS = [
  {
    label: '재료 · 시험',
    kinds: [
      { key: 'material', label: '재료' },
      { key: 'sample', label: '시료' },
      { key: 'specimen', label: '시편' },
      { key: 'test_run', label: '시험' },
    ],
  },
  {
    label: '데이터 수집 체계',
    kinds: [
      { key: 'test_type', label: '시험 정의' },
      { key: 'format_profile', label: '인풋 파일 정의' },
      { key: 'recipe', label: '레시피' },
      { key: 'connector', label: '장비 커넥터' },
    ],
  },
] as const

export const TRASH_KINDS = TRASH_GROUPS.flatMap((group) =>
  group.kinds.map((one) => one.key)
)
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
