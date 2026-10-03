/**
 * 공지를 글 하나로 — **게시판의 차례 · 번호 그대로, 본문은 적힌 그대로.**
 */

import { describe, expect, it } from 'vitest'

import type { Notice } from '@/modules/notices/api'
import { noticesAsText } from '@/modules/notices/copyAll'
import { stamp } from '@/shared/lib/datetime'

function notice(over: Partial<Notice> = {}): Notice {
  return {
    id: 'n1',
    title: '공지',
    body: '본문',
    is_published: true,
    is_popup: false,
    created_at: '2026-09-20T00:00:00Z',
    published_at: '2026-09-20T00:00:00Z',
    is_read: true,
    created_by: '시스템 관리자',
    from_release: false,
    ...over,
  }
}

const AT = new Date('2026-10-03T06:00:00Z')

describe('noticesAsText', () => {
  it('최근 것부터, 번호는 게시판과 같이 가장 오래된 것이 1 이다', () => {
    const text = noticesAsText(
      [
        notice({ id: 'n3', title: '새 기능', body: '■ 고치는 곳\n**굵게** 와 `코드`' }),
        notice({ id: 'n2', title: '점검 안내', body: '토요일 점검' }),
        notice({ id: 'n1', title: '첫 공지', body: '환영합니다' }),
      ],
      { total: 3, at: AT }
    )
    expect(text.startsWith('# MatNexus 공지 — 3건\n')).toBe(true)
    const order = ['## 3. 새 기능', '## 2. 점검 안내', '## 1. 첫 공지'].map((one) =>
      text.indexOf(one)
    )
    expect(order.every((at) => at > 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    // 본문은 적힌 그대로 — 강조 표기를 떼면 무엇이 중요한지가 사라진다.
    expect(text).toContain('■ 고치는 곳\n**굵게** 와 `코드`')
    expect(text.split('\n---\n').length).toBe(4) // 머리 + 세 건
  })

  it('누가 · 언제 · 초안 · 팝업을 머리줄 아래에 적는다 — 배포 안내는 그렇게', () => {
    const text = noticesAsText(
      [
        notice({ title: '배포', created_by: null, from_release: true, is_published: false }),
        notice({ id: 'n2', title: '팝업', is_popup: true }),
      ],
      { total: 2, at: AT }
    )
    expect(text).toContain(
      `## 2. 배포\n\n올린 사람 배포 안내 · 올린 날짜 ${stamp('2026-09-20T00:00:00Z')} · 초안`
    )
    expect(text).toContain('## 1. 팝업\n\n올린 사람 시스템 관리자 · 올린 날짜')
    expect(text).toContain(' · 팝업\n')
  })

  it('걸러 모았으면 머리에 적고, 다 못 모았으면 그렇다고 말한다', () => {
    const text = noticesAsText([notice({ title: '점검 안내' })], {
      total: 2500,
      q: '점검',
      unread: true,
      at: AT,
    })
    expect(text).toContain(`모은 때 ${stamp(AT.toISOString())} · 찾기 「점검」 · 안 읽은 것만`)
    expect(text).toContain('전체 2500건 중 1건만 모았습니다')
    expect(text).toContain('## 2500. 점검 안내')
  })
})
