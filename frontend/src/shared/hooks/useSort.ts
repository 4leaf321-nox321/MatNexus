/**
 * 표 정렬 상태 — **세 표가 같게 움직이고, 이 브라우저가 기억한다.**
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
 *
 * ## 어디에 기억하나 — **브라우저다. 계정이 아니다**
 *
 *     같은 PC 로 다시 접속       따라온다
 *     같은 계정, 다른 PC          안 따라온다
 *     같은 PC 를 다른 사람이 쓸 때  앞사람 설정이 보인다
 *
 * 마지막 줄이 유일하게 걸리는 자리인데, 정렬은 **데이터가 아니라 보는 방식**이라
 * 남에게 새어도 잃을 것이 없다. 계정별로 하려면 서버에 저장해야 하고, 그러면
 * 표가 늘 때마다 스키마가 커진다 — 값에 비해 비싸다.
 *
 * **거르기는 안 기억한다.** 남겨 두면 다음에 열었을 때 목록이 왜 짧은지 모른다.
 * 정렬은 무엇이 보이는지를 안 바꾸므로 기억해도 그런 일이 없다.
 */

import { useEffect, useState } from 'react'

export interface SortState {
  key: string
  descending: boolean
}

const PREFIX = 'matnexus.sort.'

/**
 * 적어 둔 것을 읽는다. **믿지 않고 확인한다.**
 *
 * 저장된 열 이름이 지금도 정렬할 수 있는 열이라는 보장이 없다 — 표에서 열을
 * 빼면 서버가 422 를 내고, 그러면 **그 브라우저에서는 목록이 영영 안 뜬다.**
 * 사람은 자기 브라우저만 고장 난 이유를 알 수 없다.
 */
function restore(name: string, allowed: readonly string[] | undefined): SortState | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + name)
    if (!raw) return null
    const found = JSON.parse(raw) as Partial<SortState>
    if (typeof found.key !== 'string' || typeof found.descending !== 'boolean') return null
    if (allowed && !allowed.includes(found.key)) return null
    return { key: found.key, descending: found.descending }
  } catch {
    // 개인 정보 보호 모드·저장 공간 꽉 참. **정렬 하나 때문에 화면이 죽으면 안 된다.**
    return null
  }
}

export function useSort(
  initial: string,
  options: {
    /** 이 표를 가리키는 이름. 주면 이 브라우저가 기억한다. */
    remember?: string
    /** 정렬할 수 있는 열. 저장된 값이 여기 없으면 버린다. */
    allowed?: readonly string[]
    descending?: boolean
  } = {}
) {
  const { remember, allowed, descending = true } = options
  const [sort, setSort] = useState<SortState>(
    () => (remember && restore(remember, allowed)) || { key: initial, descending }
  )

  useEffect(() => {
    if (!remember) return
    try {
      window.localStorage.setItem(PREFIX + remember, JSON.stringify(sort))
    } catch {
      // 못 적어도 이번 화면은 그대로 돈다. 다음에 안 따라올 뿐이다.
    }
  }, [remember, sort])

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
