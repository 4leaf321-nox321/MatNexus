/**
 * 본문 폭 — **어느 화면이 상한을 푸나.**
 *
 * 폭을 화면이 스스로 정하면 규칙이 흩어진다(`boundaries.test.ts` 가 막는다).
 * 대신 AppShell 이 경로로 정하는데, **그 목록은 늘어나기 쉽다** — 「이 화면도
 * 좁아 보이니 넣자」 가 반복되면 결국 전부가 넓어지고, 그때는 상한을 둔 이유가
 * 사라진다.
 *
 * 그래서 여기서 못을 박는다: **표만 그리는 목록 화면은 넣지 않는다.** 4K 에서
 * 한 줄이 화면을 가로지르면 눈이 행을 놓친다.
 */

import { describe, expect, it } from 'vitest'

import { WIDE } from '@/shared/layout/AppShell'

const wide = (path: string) => WIDE.some((one) => one.test(path))

describe('상한을 푸는 화면', () => {
  it('상세 둘은 넓다 — 목록과 내용이 좌우로 갈리는 화면이다', () => {
    expect(wide('/test-runs/2f0a1b3c-0000-4000-8000-000000000001')).toBe(true)
    expect(wide('/materials/2f0a1b3c-0000-4000-8000-000000000001')).toBe(true)
  })

  it('목록 화면은 넓히지 않는다', () => {
    // 재료 목록은 표 하나뿐이라 폭이 곧 줄 길이가 된다.
    expect(wide('/materials')).toBe(false)
    expect(wide('/tests')).toBe(false)
    expect(wide('/specimens')).toBe(false)
    expect(wide('/cards')).toBe(false)
  })

  it('하위 경로까지 넓어지지 않는다', () => {
    // `/materials/<id>/무언가` 가 생기면 그때 다시 판단한다 — 조용히 따라오면
    // 그 화면이 왜 넓은지 아무도 모른다.
    expect(wide('/materials/abc/edit')).toBe(false)
  })
})
