/**
 * 표 정렬 상태 — **세 표가 같게 움직인다.**
 *
 * 화면마다 따로 적으면 한쪽은 눌렀을 때 오름차순부터, 다른 쪽은 내림차순부터
 * 시작한다. 같은 표처럼 생긴 것이 다르게 움직이면 사람은 매번 눌러 보고 확인한다.
 *
 * ## 누르면 뒤집는다. 다른 열이면 그 열로 간다
 *
 * 세 번째 상태(정렬 없음)를 두지 않는다. **목록에는 늘 순서가 있다** — 「정렬
 * 없음」 은 DB 가 주는 대로라는 뜻이고, 그건 쪽마다 달라질 수 있어 순서가 아니다.
 *
 * ## 새 열은 내림차순부터
 *
 * 등록 일시·시험일처럼 **최근 것이 궁금한 열**이 많다. 오름차순부터 시작하면
 * 거의 매번 두 번 눌러야 한다.
 */

import { useState } from 'react'

export interface SortState {
  key: string
  descending: boolean
}

export function useSort(initial: string, descending = true) {
  const [sort, setSort] = useState<SortState>({ key: initial, descending })

  /** 그 열을 눌렀을 때. 같은 열이면 뒤집고, 다른 열이면 내림차순으로 간다. */
  function toggle(key: string) {
    setSort((now) =>
      now.key === key ? { key, descending: !now.descending } : { key, descending: true }
    )
  }

  /** 열 머리에 넘기는 것. `key` 만 채우면 된다. */
  function handle(key: string) {
    return { key, active: sort.key, descending: sort.descending, onSort: toggle }
  }

  return { sort, handle }
}
