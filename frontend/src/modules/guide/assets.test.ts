/**
 * 그림 불러오기 — **깨진 그림 75개가 여기서 났다.**
 *
 * 무는 자리를 「blob 주소가 나온다」 보다 **「토큰을 실어 받는가」**·「SVG 에 지금
 * 화면의 색을 심는가」·「작성자가 정한 색을 안 덮는가」 에 둔다. 앞엣것이 틀리면
 * 그림이 아예 안 뜨고, 뒤엣것이 틀리면 다크 모드에서만 조용히 안 보인다.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearAssetCache, loadAsset, themeOf, withTheme } from '@/modules/guide/assets'

const fetchWithAuth = vi.fn()
vi.mock('@/shared/api/client', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args),
}))

const SVG = '<svg viewBox="0 0 10 10"><style>.hot{fill:#B33C29}</style><path/></svg>'
const THEME = { ink: 'rgb(231, 235, 229)', background: 'rgb(15, 20, 17)' }

function reply(body: string, type: string) {
  return {
    ok: true,
    headers: { get: () => type },
    text: () => Promise.resolve(body),
    blob: () => Promise.resolve(new Blob([body], { type })),
  }
}

beforeEach(() => {
  clearAssetCache()
  fetchWithAuth.mockReset()
  let n = 0
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: () => `blob:fake/${++n}`,
    revokeObjectURL: () => {},
  })
})

afterEach(() => vi.unstubAllGlobals())

describe('색 심기', () => {
  it('여는 태그 바로 뒤에 넣는다 — 작성자가 정한 색을 안 덮는다', () => {
    // 뒤에 넣으면 그림의 강조색(빨강 경고선)이 전부 글자색이 된다.
    const out = withTheme(SVG, THEME)
    expect(out.indexOf('color:rgb(231, 235, 229)')).toBeLessThan(out.indexOf('.hot'))
    // 여는 태그가 끝나자마자다 — 그림의 첫 요소보다 앞.
    expect(out.indexOf('<style>svg{')).toBeLessThan(out.indexOf('<path'))
  })

  it('currentColor 가 풀릴 색과 var(--bg) 를 함께 준다', () => {
    // 본문 SVG 에 currentColor 가 2342곳, var(--bg) 가 18곳이다. 하나만 주면
    // 나머지는 여전히 검정으로 풀린다.
    const out = withTheme(SVG, THEME)
    expect(out).toContain('color:rgb(231, 235, 229)')
    expect(out).toContain('--bg:rgb(15, 20, 17)')
  })

  it('xmlns 를 넣는다 — 없으면 파일로서는 아무것도 안 그려진다', () => {
    // HTML 안에서는 문맥으로 SVG 인 줄 알지만, 파일로 떼면 XML 로 읽힌다.
    // 요청은 200 이라 네트워크 탭에는 표시가 없고 그림 자리만 빈다.
    expect(withTheme(SVG, THEME)).toContain('xmlns="http://www.w3.org/2000/svg"')
  })

  it('이미 있으면 두 번 넣지 않는다', () => {
    const already = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'
    expect(withTheme(already, THEME).match(/xmlns=/g)).toHaveLength(1)
  })

  it('&nbsp; 를 숫자 엔티티로 바꾼다 — 하나만 있어도 문서 전체가 안 그려진다', () => {
    // XML 이 이름으로 아는 것은 다섯뿐이다(amp·lt·gt·quot·apos).
    const out = withTheme('<svg viewBox="0 0 1 1"><text>3&nbsp;mm</text></svg>', THEME)
    expect(out).toContain('&#160;')
    expect(out).not.toContain('&nbsp;')
  })

  it('고치고 나면 XML 로 읽힌다', () => {
    // 이 시험이 요점이다 — 위 셋을 다 해도 파싱이 안 되면 안 그려진다.
    const out = withTheme('<svg viewBox="0 0 1 1"><text>3&nbsp;mm</text></svg>', THEME)
    const parsed = new DOMParser().parseFromString(out, 'image/svg+xml')
    expect(parsed.querySelector('parsererror')).toBeNull()
  })

  it('svg 태그가 없으면 손대지 않는다', () => {
    expect(withTheme('그냥 글', THEME)).toBe('그냥 글')
  })
})

describe('받아 오기', () => {
  it('토큰을 실어 받는다 — <img> 가 못 하는 일이 이것이다', async () => {
    fetchWithAuth.mockResolvedValue(reply(SVG, 'image/svg+xml'))
    const url = await loadAsset('/api/guide/assets/abc', THEME)
    expect(fetchWithAuth).toHaveBeenCalledWith('/api/guide/assets/abc')
    expect(url).toMatch(/^blob:/)
  })

  it('SVG 가 아니면 색을 안 심는다', async () => {
    // PNG 를 글로 읽으면 깨진다. 사람이 올린 사진이 이 길로 온다.
    fetchWithAuth.mockResolvedValue(reply('\x89PNG', 'image/png'))
    await loadAsset('/api/guide/assets/png', THEME)
    expect(fetchWithAuth).toHaveBeenCalledOnce()
  })

  it('테마가 다르면 다시 받는다 — 색이 굳으면 안 된다', async () => {
    fetchWithAuth.mockResolvedValue(reply(SVG, 'image/svg+xml'))
    await loadAsset('/api/guide/assets/abc', THEME)
    await loadAsset('/api/guide/assets/abc', THEME)
    expect(fetchWithAuth).toHaveBeenCalledTimes(1)
    await loadAsset('/api/guide/assets/abc', { ink: 'rgb(23, 33, 30)', background: '#EDEFEC' })
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
  })

  it('실패는 기억하지 않는다 — 잠깐 끊긴 것을 영영 붙들면 새로고침해야 낫는다', async () => {
    fetchWithAuth.mockResolvedValue({ ok: false, status: 401, headers: { get: () => '' } })
    await expect(loadAsset('/api/guide/assets/x', THEME)).rejects.toThrow('401')
    fetchWithAuth.mockResolvedValue(reply(SVG, 'image/svg+xml'))
    await expect(loadAsset('/api/guide/assets/x', THEME)).resolves.toMatch(/^blob:/)
  })
})

describe('테마 읽기', () => {
  it('코드에 적은 팔레트가 아니라 살아 있는 요소에서 읽는다', () => {
    // 토큰을 고치면 그림만 옛 색으로 남는 일을 막는다.
    const box = document.createElement('div')
    box.style.color = 'rgb(1, 2, 3)'
    document.body.appendChild(box)
    expect(themeOf(box).ink).toBe('rgb(1, 2, 3)')
    box.remove()
  })
})
