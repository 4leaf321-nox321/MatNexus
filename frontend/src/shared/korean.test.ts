/**
 * 조사 — **「시험 를 담습니다」 를 안 쓴다.**
 *
 * 낱말을 표에서 읽어 문장을 만들면 조사가 따라 바뀐다. 틀린 조사는 화면 전체를
 * 기계가 쓴 것처럼 읽히게 만든다.
 */

import { describe, expect, it } from 'vitest'

import { withJosa } from '@/shared/korean'

describe('받침을 보고 고른다', () => {
  it('받침이 있으면 을·이·은·과', () => {
    expect(withJosa('시험', '을/를')).toBe('시험을')
    expect(withJosa('시험', '이/가')).toBe('시험이')
    expect(withJosa('시험', '은/는')).toBe('시험은')
    expect(withJosa('시험', '과/와')).toBe('시험과')
  })

  it('받침이 없으면 를·가·는·와', () => {
    expect(withJosa('카드', '을/를')).toBe('카드를')
    expect(withJosa('재료', '이/가')).toBe('재료가')
    expect(withJosa('재료', '은/는')).toBe('재료는')
    expect(withJosa('카드', '과/와')).toBe('카드와')
  })
})

describe('모르는 것에는 안 붙인다', () => {
  it('한글이 아닌 글자로 끝나면 그대로 둔다', () => {
    // 「DMA를」 인지 「DMA을」 인지는 읽는 법에 달렸다 — **틀린 조사보다 없는 편이 낫다.**
    expect(withJosa('DMA', '을/를')).toBe('DMA')
    expect(withJosa('E2', '이/가')).toBe('E2')
  })

  it('빈 낱말에도 안 붙인다', () => {
    expect(withJosa('', '을/를')).toBe('')
    expect(withJosa('   ', '이/가')).toBe('   ')
  })
})
