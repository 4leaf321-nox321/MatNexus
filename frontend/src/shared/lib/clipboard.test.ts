/**
 * 클립보드 — **되돌아 갈 길이 실제로 되는가.**
 *
 * 길을 만들어 두는 것과 그 길이 통하는 것은 다르다. 실제로 사내 IP(`http://`)
 * 에서 「표 복사」가 안 됐고, 되돌아 갈 길이 있었는데도 안 됐다.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { copyText } from '@/shared/lib/clipboard'

/** `execCommand('copy')` 가 불렸을 때 화면에 무엇이 있었나. */
let seen: { text: string; parent: string | null } | null = null

function stubExecCommand(result = true) {
  return vi.fn(() => {
    const box = document.querySelector('textarea[aria-hidden="true"]')
    seen = box
      ? {
          text: (box as HTMLTextAreaElement).value,
          parent: box.parentElement?.getAttribute('role') ?? box.parentElement?.tagName ?? null,
        }
      : null
    return result
  })
}

function secure(on: boolean) {
  Object.defineProperty(window, 'isSecureContext', { value: on, configurable: true })
}

beforeEach(() => {
  seen = null
  document.body.innerHTML = ''
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('보안 컨텍스트가 아닐 때', () => {
  it('비동기 API 를 아예 안 건드린다', async () => {
    // **거절을 기다리는 순간 사용자 몸짓이 끝난다.** 그러면 되돌아 갈 길까지
    // 막혀서, 두 길을 만들어 둔 뜻이 없어진다.
    const writeText = vi.fn(() => Promise.reject(new Error('denied')))
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    secure(false)
    document.execCommand = stubExecCommand()

    expect(await copyText('가나다')).toBe(true)
    expect(writeText).not.toHaveBeenCalled()
    expect(seen?.text).toBe('가나다')
  })

  it('숨은 칸으로 복사한다', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined })
    secure(false)
    document.execCommand = stubExecCommand()
    expect(await copyText('값')).toBe(true)
  })

  it('막히면 거짓을 돌려준다', async () => {
    // **조용히 성공한 척하면 안 된다.** 사람은 복사가 됐다고 믿고 빈 칸을
    // 붙여 넣는다 — 부르는 쪽이 그 사실을 말할 수 있어야 한다.
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined })
    secure(false)
    document.execCommand = stubExecCommand(false)
    expect(await copyText('값')).toBe(false)
  })
})

describe('모달이 열려 있을 때', () => {
  it('숨은 칸을 모달 안에 붙인다', async () => {
    // **바깥은 `aria-hidden`/inert 다.** `body` 에 붙이면 `select()` 가 쓸 수
    // 있는 선택을 못 만들고, 빈 것이 복사된다 — 실제로 그래서 안 됐다.
    const modal = document.createElement('div')
    modal.setAttribute('role', 'dialog')
    const button = document.createElement('button')
    modal.appendChild(button)
    document.body.appendChild(modal)
    button.focus()

    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined })
    secure(false)
    document.execCommand = stubExecCommand()

    await copyText('표')
    expect(seen?.parent).toBe('dialog')
  })

  it('모달이 없으면 body 로 충분하다', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined })
    secure(false)
    document.execCommand = stubExecCommand()

    await copyText('표')
    expect(seen?.parent).toBe('BODY')
  })
})

describe('보안 컨텍스트일 때', () => {
  it('비동기 API 를 쓴다', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    secure(true)
    document.execCommand = stubExecCommand()

    expect(await copyText('값')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('값')
    expect(seen).toBeNull()
  })

  it('거절당하면 숨은 칸으로 한 번 더 해 본다', async () => {
    const writeText = vi.fn(() => Promise.reject(new Error('denied')))
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    secure(true)
    document.execCommand = stubExecCommand()

    expect(await copyText('값')).toBe(true)
    expect(seen?.text).toBe('값')
  })
})

describe('뒤처리', () => {
  it('숨은 칸을 남기지 않는다', async () => {
    // 남으면 다음 복사가 그것을 찾고, 화면에도 쌓인다.
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined })
    secure(false)
    document.execCommand = stubExecCommand()

    await copyText('값')
    expect(document.querySelector('textarea')).toBeNull()
  })
})
