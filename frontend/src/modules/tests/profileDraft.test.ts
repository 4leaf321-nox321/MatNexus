/**
 * 임시 저장 — **잃지 않는가, 그리고 잘못 되살리지 않는가.**
 *
 * 되살리는 쪽이 조용히 틀리면 임시 저장이 없느니만 못하다. 반쯤 채워진 화면을
 * 사람이 다 채운 것으로 알고 저장하기 때문이다.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DRAFT_VERSION,
  forgetDraft,
  readDraft,
  since,
  writeDraft,
} from '@/modules/tests/profileDraft'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('왕복', () => {
  it('적은 것을 그대로 돌려준다', () => {
    expect(writeDraft('ta_dma850', { include: '^Temp' }, 'a.csv', '2026-08-26T10:00:00Z')).toBe(
      true
    )
    const back = readDraft('ta_dma850')
    expect(back?.state).toEqual({ include: '^Temp' })
    expect(back?.fileName).toBe('a.csv')
  })

  it('새로 만들기와 편집이 안 섞인다', () => {
    // 섞이면 새 프로파일을 만들다가 남의 프로파일 규칙을 이어받는다.
    writeDraft(undefined, { include: '새것' }, null, '2026-08-26T10:00:00Z')
    writeDraft('ta_dma850', { include: '편집' }, null, '2026-08-26T10:00:00Z')
    expect(readDraft(undefined)?.state).toEqual({ include: '새것' })
    expect(readDraft('ta_dma850')?.state).toEqual({ include: '편집' })
  })

  it('버리면 없다', () => {
    writeDraft('x', { a: 1 }, null, '2026-08-26T10:00:00Z')
    forgetDraft('x')
    expect(readDraft('x')).toBeNull()
  })

  it('없으면 null 이다', () => {
    expect(readDraft('없는것')).toBeNull()
  })
})

describe('잘못 되살리지 않는다', () => {
  it('모양이 바뀌면 안 읽는다', () => {
    // 옛 임시본을 새 화면에 밀어 넣으면 **어디가 비었는지 모르는 채로** 저장된다.
    window.localStorage.setItem(
      'matnexus.profile-draft.x',
      JSON.stringify({ version: DRAFT_VERSION + 1, at: '', fileName: null, state: {} })
    )
    expect(readDraft('x')).toBeNull()
  })

  it('깨진 글자면 안 읽는다', () => {
    window.localStorage.setItem('matnexus.profile-draft.x', '{망가짐')
    expect(readDraft('x')).toBeNull()
  })

  it('state 가 객체가 아니면 안 읽는다', () => {
    window.localStorage.setItem(
      'matnexus.profile-draft.x',
      JSON.stringify({ version: DRAFT_VERSION, at: '', fileName: null, state: '문자열' })
    )
    expect(readDraft('x')).toBeNull()
  })
})

describe('브라우저가 막을 때', () => {
  it('화면을 멈추지 않는다', () => {
    // 사생활 보호 창에서는 `localStorage` 접근 자체가 던진다. 임시 저장은
    // 거들기이지 기능이 아니므로, 안 되면 안 되는 대로 지나가야 한다.
    vi.stubGlobal('localStorage', {
      get setItem() {
        throw new Error('denied')
      },
    })
    expect(writeDraft('x', { a: 1 }, null, '2026-08-26T10:00:00Z')).toBe(false)
    expect(readDraft('x')).toBeNull()
    expect(() => forgetDraft('x')).not.toThrow()
  })

  it('한도를 넘으면 거짓을 돌려준다', () => {
    // **조용히 성공한 척하면 안 된다.** 화면이 "임시 저장을 할 수 없습니다" 를
    // 말할 수 있어야 사람이 스스로 대비한다.
    vi.stubGlobal('localStorage', {
      setItem: vi.fn((key: string) => {
        if (key !== '__matnexus__') throw new Error('quota')
      }),
      removeItem: vi.fn(),
      getItem: vi.fn(() => null),
    })
    expect(writeDraft('x', { a: 1 }, null, '2026-08-26T10:00:00Z')).toBe(false)
  })
})

describe('언제 적었나', () => {
  const base = Date.parse('2026-08-26T10:00:00Z')

  it('사람이 읽는 말로', () => {
    expect(since('2026-08-26T10:00:00Z', base)).toBe('방금')
    expect(since('2026-08-26T09:57:00Z', base)).toBe('3분 전')
    expect(since('2026-08-26T07:00:00Z', base)).toBe('3시간 전')
    expect(since('2026-08-24T10:00:00Z', base)).toBe('2일 전')
  })

  it('못 읽는 값이면 빈 글자다', () => {
    expect(since('언제', base)).toBe('')
  })
})
