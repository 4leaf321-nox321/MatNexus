/**
 * 목록 전부 받아 오기 — **서버 상한을 지키면서.**
 *
 * 서버는 한 응답에 200건까지만 준다(`shared/pagination.py`). 그 상한을 올려
 * 달라는 요구가 자연스럽게 나오는데, 올리면 언젠가 `?limit=1000000` 이 나가고
 * 악의가 없어도 그렇게 된다 — 화면이 '전부' 를 구현하면서 큰 수를 넣기 때문이다.
 *
 * 그래서 **상한은 그대로 두고 화면이 이어 받는다.** 서버가 한 번에 만드는 응답
 * 크기는 변하지 않고, 사용자는 전부 본다.
 *
 * 다만 **무한히 받지는 않는다.** 수만 건을 한 화면에 그리면 브라우저가 멈추고,
 * 그때 사용자는 "느리다" 가 아니라 "고장났다" 로 읽는다. 천장에 닿으면 거기서
 * 멈추고 **몇 건에서 멈췄는지 말한다** — 조용히 자르는 것이 가장 나쁘다.
 */

/** 한 요청의 상한. 서버 `MAX_LIMIT` 과 같은 값이다. */
export const PAGE_MAX = 200

/**
 * '전체' 로 받을 수 있는 최대. 200건씩 10번이다.
 *
 * 이 수의 근거는 **화면**이지 서버가 아니다 — 표 2,000줄은 스크롤로 훑을 수
 * 있는 마지막쯤이고, 그보다 많으면 검색으로 좁히는 것이 실제로 빠르다.
 */
export const ALL_MAX = 2000

/**
 * 서버 목록 응답의 모양(`shared/pagination.py` 의 `Page`).
 *
 * 모아 온 결과도 **같은 모양으로 돌려준다.** 다르면 화면이 두 갈래를 따로
 * 다뤄야 하고, 그 갈래는 언젠가 한쪽만 고쳐진다.
 */
export interface PageLike<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/**
 * 쪽을 이어 받아 모은다.
 *
 * `total` 을 첫 응답에서 받으므로 몇 번 더 부를지 바로 안다 — 없으면 "다음 쪽이
 * 있나" 를 알려고 한 건 더 요청하는 편법을 쓰게 되고, 그 편법은 화면마다 다르다.
 */
export async function fetchAll<T>(
  fetchPage: (limit: number, offset: number) => Promise<PageLike<T>>
): Promise<PageLike<T>> {
  const first = await fetchPage(PAGE_MAX, 0)
  const items = [...first.items]
  const wanted = Math.min(first.total, ALL_MAX)

  while (items.length < wanted) {
    const next = await fetchPage(PAGE_MAX, items.length)
    if (next.items.length === 0) break // 서버가 더 줄 것이 없다 — 무한 반복을 막는다
    items.push(...next.items)
  }

  const collected = items.slice(0, ALL_MAX)
  // **천장에 걸렸는지는 `items.length < total` 로 드러난다.** 따로 깃발을 두면
  // 화면이 그것을 안 볼 수 있고, 그러면 조용히 잘린 목록이 된다.
  return { items: collected, total: first.total, limit: collected.length, offset: 0 }
}
