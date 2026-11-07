/**
 * VOC 여러 건을 글 하나로 — **게시판의 번호 · 차례 그대로, 이력은 등록을 빼고 시간순.**
 */

import { describe, expect, it } from 'vitest'

import type { VocContent, VocEvent } from '@/modules/voc/api'
import { rangeLabel, vocAsText } from '@/modules/voc/copyAll'
import { stamp } from '@/shared/lib/datetime'

function event(over: Partial<VocEvent> = {}): VocEvent {
  return {
    id: 'e1',
    at: '2026-10-02T01:00:00Z',
    by: '관리자',
    from_status: 'open',
    to_status: 'accepted',
    to_status_label: '접수',
    note: null,
    ...over,
  }
}

const REGISTERED = event({ id: 'e0', from_status: null, to_status: 'open', to_status_label: '등록' })

function content(over: Partial<VocContent> = {}): VocContent {
  return {
    id: 'v1',
    seq: 12,
    title: '목록이 느려요',
    status: 'open',
    status_label: '등록',
    page_path: null,
    created_at: '2026-10-01T00:00:00Z',
    created_by: '홍길동',
    body: '목록이 느립니다',
    events: [REGISTERED],
    attachments: [],
    ...over,
  }
}

const AT = new Date('2026-11-07T06:00:00Z')

describe('vocAsText', () => {
  it('받은 차례(최신이 위)로, 번호는 게시판의 번호다', () => {
    const text = vocAsText(
      [content({ id: 'v30', seq: 30, title: '셋째' }), content({ id: 'v12', seq: 12, title: '첫째' })],
      { total: 2, at: AT }
    )
    expect(text.startsWith('# MatNexus VOC — 2건\n')).toBe(true)
    expect(text.indexOf('## 30. 셋째')).toBeGreaterThan(0)
    expect(text.indexOf('## 30. 셋째')).toBeLessThan(text.indexOf('## 12. 첫째'))
    expect(text.split('\n---\n').length).toBe(3) // 머리 + 두 건
  })

  it('머리줄 아래 상태 · 누가 · 언제 · 화면 · 첨부, 그 아래 본문', () => {
    const text = vocAsText(
      [
        content({
          status_label: '처리 중',
          page_path: '/w/metal/tests',
          attachments: ['캡처.png', '로그.txt'],
          body: '  첫 줄\n**둘째 줄**  ',
        }),
      ],
      { total: 1, at: AT }
    )
    expect(text).toContain(
      `## 12. 목록이 느려요\n\n상태 처리 중 · 올린 사람 홍길동 · 올린 날짜 ${stamp('2026-10-01T00:00:00Z')}` +
        ' · 화면 /w/metal/tests · 첨부 캡처.png, 로그.txt\n\n첫 줄\n**둘째 줄**'
    )
  })

  it('이력은 등록을 빼고, 옮김과 댓글을 시간순으로 — 말은 줄 아래 들여 적는다', () => {
    const text = vocAsText(
      [
        content({
          events: [
            REGISTERED,
            event({ note: '보겠습니다' }),
            event({
              id: 'e2',
              at: '2026-10-03T01:00:00Z',
              by: null,
              from_status: 'accepted',
              to_status: 'accepted',
              note: '재현됩니다\n\n순서: 열기 → 누르기',
            }),
          ],
        }),
      ],
      { total: 1, at: AT }
    )
    expect(text).toContain(
      '### 이력\n\n' +
        `- ${stamp('2026-10-02T01:00:00Z')} · 관리자 · 접수 로 옮김\n  보겠습니다\n` +
        `- ${stamp('2026-10-03T01:00:00Z')} · 알 수 없음 · 댓글\n  재현됩니다\n\n  순서: 열기 → 누르기`
    )
    expect(text).not.toContain('등록 로 옮김')
  })

  it('등록만 있으면 이력 절이 없다', () => {
    expect(vocAsText([content()], { total: 1, at: AT })).not.toContain('### 이력')
  })

  it('무엇을 모았는지 머리에 적는다 — 번호 범위와 거른 조건', () => {
    const text = vocAsText([content()], {
      total: 1,
      seqFrom: 10,
      seqTo: 30,
      statusLabel: '해결',
      q: '느려',
      mine: true,
      at: AT,
    })
    expect(text).toContain(
      `모은 때 ${stamp(AT.toISOString())} · 번호 10~30 · 상태 「해결」 · 찾기 「느려」 · 내가 낸 것만`
    )
  })

  it('고른 것이면 고른 수를 적고, 그 사이 지워진 건이 있으면 그렇다고 말한다', () => {
    const text = vocAsText([content()], { total: 3, picked: true, q: '무시', at: AT })
    expect(text).toContain(`모은 때 ${stamp(AT.toISOString())} · 고른 3건\n`)
    expect(text).toContain('고른 3건 중 1건만 찾았습니다')
    // 고른 것은 거르기와 상관없다 — 거른 조건을 적으면 거짓말이다.
    expect(text).not.toContain('찾기')
  })

  it('범위에서 다 못 모았으면 그렇다고 말한다', () => {
    const text = vocAsText([content()], { total: 2500, at: AT })
    expect(text).toContain('전체 2500건 중 1건만 모았습니다')
  })
})

describe('rangeLabel', () => {
  it('양끝 · 한쪽 · 같은 번호 · 없음', () => {
    expect(rangeLabel(10, 30)).toBe('번호 10~30')
    expect(rangeLabel(10, undefined)).toBe('번호 10부터')
    expect(rangeLabel(undefined, 30)).toBe('번호 30까지')
    expect(rangeLabel(7, 7)).toBe('번호 7')
    expect(rangeLabel()).toBeNull()
  })
})
