/**
 * '전체' 로 받기 — **서버 상한을 지키면서 전부 모으는가.**
 *
 * 두 가지가 어긋나기 쉽다: 요청 하나가 상한을 넘는 것과, 천장에서 조용히
 * 잘리는 것. 둘 다 화면에서는 안 보이므로 여기서 잡는다.
 */

import { describe, expect, it } from 'vitest'

import { ALL_MAX, PAGE_MAX, fetchAll } from '@/shared/api/paging'

/** `total` 건을 가진 가짜 서버. 요청한 limit 을 그대로 기록한다. */
function server(total: number) {
  const asked: number[] = []
  return {
    asked,
    page: async (limit: number, offset: number) => {
      asked.push(limit)
      const size = Math.min(limit, PAGE_MAX)
      return {
        items: Array.from({ length: Math.max(0, Math.min(size, total - offset)) }, (_, i) => offset + i),
        total,
        limit: size,
        offset,
      }
    },
  }
}

describe('fetchAll', () => {
  it('여러 쪽을 이어 받아 전부 모은다', async () => {
    const fake = server(437)
    const result = await fetchAll(fake.page)
    expect(result.items).toHaveLength(437)
    expect(result.items[436]).toBe(436)
    expect(result.total).toBe(437)
  })

  it('한 요청이 서버 상한을 넘지 않는다', async () => {
    // **여기가 이 함수의 존재 이유다.** 상한을 올려 달라는 요구를 그대로
    // 받으면 언젠가 `?limit=1000000` 이 나간다.
    const fake = server(437)
    await fetchAll(fake.page)
    expect(Math.max(...fake.asked)).toBeLessThanOrEqual(PAGE_MAX)
    expect(fake.asked).toHaveLength(3) // 200 + 200 + 37
  })

  it('한 쪽에 다 들어가면 한 번만 부른다', async () => {
    const fake = server(12)
    const result = await fetchAll(fake.page)
    expect(result.items).toHaveLength(12)
    expect(fake.asked).toHaveLength(1)
  })

  it('천장에서 멈추되 전체 건수는 그대로 말한다', async () => {
    // 조용히 자르면 화면이 "이게 전부" 라고 믿는다. `total` 이 남아 있어야
    // `items.length < total` 로 잘렸다는 것이 드러난다.
    const fake = server(ALL_MAX + 500)
    const result = await fetchAll(fake.page)
    expect(result.items).toHaveLength(ALL_MAX)
    expect(result.total).toBe(ALL_MAX + 500)
  })

  it('서버가 빈 쪽을 주면 멈춘다', async () => {
    // total 을 크게 말해 놓고 실제로는 안 주는 서버. 없으면 무한 반복이다.
    let calls = 0
    const result = await fetchAll(async (limit, offset) => {
      calls += 1
      return { items: offset === 0 ? [1, 2, 3] : [], total: 999, limit, offset }
    })
    expect(result.items).toHaveLength(3)
    expect(calls).toBe(2)
  })
})
