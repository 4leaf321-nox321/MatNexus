/**
 * 복사는 **HTTP 로 열어도 돼야 한다.**
 *
 * `navigator.clipboard` 는 보안 컨텍스트에서만 있다 — HTTPS 이거나 `localhost`
 * 일 때다. 사내망 IP 로 HTTP 로 열면 그 객체 자체가 없어서, 그것만 쓰면 복사가
 * **개발 기계에서는 되고 실제 쓰는 자리에서만 조용히 안 된다.** 그런 실패가 가장
 * 늦게 발견된다.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyText } from '@/shared/clipboard'

function secure(value: boolean) {
  Object.defineProperty(window, 'isSecureContext', { value, configurable: true })
}

function withClipboard(writeText: () => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
}

/** jsdom 에는 `execCommand` 가 아예 없다 — 실제 브라우저에는 있다. */
function withExec(result: boolean) {
  const exec = vi.fn(() => result)
  Object.defineProperty(document, 'execCommand', { value: exec, configurable: true })
  return exec
}

afterEach(() => {
  vi.restoreAllMocks()
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
})

describe('클립보드', () => {
  it('보안 컨텍스트면 클립보드 API 를 쓴다', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    secure(true)
    withClipboard(writeText)

    expect(await copyText('가\t나')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('가\t나')
  })

  it('HTTP 면 옛 길로 간다', async () => {
    // **이 파일의 이유.** 여기서 안 되면 사내망에서 복사 버튼이 죽는다.
    const writeText = vi.fn(() => Promise.resolve())
    secure(false)
    withClipboard(writeText)
    const exec = withExec(true)

    expect(await copyText('가\t나')).toBe(true)
    expect(writeText).not.toHaveBeenCalled()
    expect(exec).toHaveBeenCalled()
  })

  it('클립보드 API 가 거부해도 옛 길로 되돌아간다', async () => {
    secure(true)
    withClipboard(() => Promise.reject(new Error('권한 없음')))
    const exec = withExec(true)

    expect(await copyText('가')).toBe(true)
    expect(exec).toHaveBeenCalled()
  })

  it('둘 다 막히면 거짓을 돌려준다', async () => {
    // **화면이 다른 길을 보여 줄 수 있어야 한다.** 버튼만 눌리고 아무 일도 안
    // 일어나는 것이 가장 나쁘다.
    secure(false)
    withExec(false)

    expect(await copyText('가')).toBe(false)
  })

  it('상자를 남기지 않는다', async () => {
    secure(false)
    withExec(true)

    await copyText('가')
    expect(document.querySelectorAll('textarea')).toHaveLength(0)
  })
})
