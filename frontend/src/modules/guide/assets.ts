/**
 * 핸드북 그림 불러오기 — **`<img src>` 로는 못 받고, 받아도 페이지를 모른다.**
 *
 * 두 가지를 여기서 함께 푼다. 둘 다 「그림이 따로 있는 파일이 됐다」 는 한 원인에서
 * 나온다 — 원본 HTML 에서는 SVG 가 본문 안에 있었고, 씨앗을 만들면서 파일로 떼어
 * 냈다(`guide_seed.mjs`).
 *
 * ## 1. 토큰이 안 실린다
 *
 * 브라우저가 스스로 여는 요청에는 Authorization 헤더가 없다. access 토큰은 메모리에만
 * 있고 쿠키가 아니라서(XSS 방어) `<img src="/api/guide/assets/…">` 는 **언제나
 * 401** 이었다 — 그림 75개가 전부 깨진 아이콘이었다. 토큰을 붙여 받아 blob 주소로
 * 바꿔 준다.
 *
 * ## 2. `<img>` 안의 SVG 는 격리된 문서다
 *
 * 페이지의 것을 하나도 못 쓴다. 그런데 이 SVG 들은 **본문에 인라인될 것으로** 그려져
 * 있다 — `currentColor` 가 2342곳, `var(--bg)` 가 18곳이다. 격리되면 `currentColor`
 * 는 페이지 글자색이 아니라 SVG 자신의 기본값(검정)으로 풀리고, 다크 모드에서 선과
 * 글자가 어두운 바탕에 검정으로 그려져 **안 보인다.**
 *
 * 그래서 받아 온 SVG 에 **지금 화면의 색을 심어 준다.** 팔레트를 코드에 적지 않고
 * 살아 있는 요소에서 읽는다(`getComputedStyle`) — 그래야 테마를 고쳐도 따라온다.
 *
 * **`@media (prefers-color-scheme)` 를 SVG 안에 넣는 길은 안 썼다.** 이 앱의 다크
 * 모드는 OS 설정이 아니라 **사람이 누르는 토글**이라(`ThemeProvider`), OS 는 밝고
 * 앱만 어두운 상태에서 그림만 밝게 남는다.
 *
 * ## 글꼴은 되살릴 수 없다
 *
 * 원본은 Google Fonts 로 IBM Plex 를 받아 썼다. 폐쇄망에서는 못 받고, `<img>` 안의
 * SVG 는 앱이 가진 글꼴도 못 쓴다 — 그 문서가 쓸 수 있는 것은 **OS 에 깔린 글꼴**
 * 뿐이다. 그래서 여기서는 되살리는 대신 **떨어지는 자리를 정해 준다**: 한글이
 * 지정한 글꼴에 없으면 브라우저가 글자마다 딴 글꼴을 찾아 넣는데, 그때 자폭이 섞여
 * 라벨이 흔들린다. 한글 글꼴을 이름으로 박아 그것을 막는다.
 */

import { fetchWithAuth } from '@/shared/api/client'

/** 본문이 그림을 가리키는 주소. 이 접두사인 것만 손댄다. */
export const ASSET_PREFIX = '/api/guide/assets/'

/** 지금 화면에서 읽어 낸 그림의 바탕 조건. 테마가 바뀌면 이 값이 바뀐다. */
export interface AssetTheme {
  ink: string
  background: string
}

/**
 * 살아 있는 요소에서 색을 읽는다. **팔레트를 코드에 두지 않는다** — 테마 토큰을
 * 고치면 그림만 옛 색으로 남고, 그 어긋남은 다크 모드에서만 드러난다.
 */
export function themeOf(element: Element | null): AssetTheme {
  const target = element ?? document.body
  const style = getComputedStyle(target)
  const background = getComputedStyle(document.body).backgroundColor
  return {
    ink: style.color || '#000',
    // 투명하면 SVG 가 제 바탕을 안 그리는 편이 낫다 — 흰 사각형이 남는 것보다.
    background: background && background !== 'rgba(0, 0, 0, 0)' ? background : 'transparent',
  }
}

/**
 * 본문 안에 있던 SVG 를 **혼자 설 수 있는 파일로** 고친다.
 *
 * 셋을 한다. 셋 다 「인라인이던 것을 파일로 떼어 냈다」 는 한 원인에서 나온다.
 *
 * ## 1. `xmlns` — 없으면 아무것도 안 그려진다
 *
 * HTML 안에 있을 때는 파서가 문맥으로 SVG 인 줄 안다. **파일로 떼면 XML 로 읽히고,
 * 그때는 이름공간 선언이 필수다.** 없으면 브라우저가 그리기를 포기하는데 요청은
 * 200 이라 네트워크 탭에는 아무 표시도 없다 — 그림 자리만 빈다.
 * 실측(2026-08-29): 75개 전부 없었다.
 *
 * ## 2. `&nbsp;` — XML 은 모르는 엔티티다
 *
 * HTML 이 아는 이름 엔티티는 XML 에 없다. 하나라도 있으면 **문서 전체가 파싱
 * 오류**로 안 그려진다. 6개 파일이 그랬다.
 *
 * ## 3. 지금 화면의 색
 *
 * `currentColor` 와 `var(--bg)` 가 페이지를 기대한다(위 설명).
 *
 * **색은 맨 앞에 넣는다.** 뒤에 넣으면 그림이 스스로 정한 색을 덮어써서, 작성자가
 * 의도한 강조색(빨강 경고선 같은 것)이 전부 글자색이 된다.
 */
export function withTheme(svg: string, theme: AssetTheme): string {
  const open = svg.match(/<svg[^>]*>/)
  if (!open) return svg
  // XML 이 아는 다섯(amp·lt·gt·quot·apos) 말고는 이름으로 못 쓴다. 숫자로 바꾼다.
  svg = svg.replace(/&nbsp;/g, '&#160;')
  const style =
    '<style>' +
    `svg{color:${theme.ink};--bg:${theme.background};}` +
    // 한글 글꼴을 이름으로 박는다. IBM Plex 를 앞에 남겨 둔다 — 언젠가 깔리면
    // 그때는 원본 그대로 그려진다.
    'text,tspan{font-family:"IBM Plex Sans KR","Malgun Gothic","Apple SD Gothic Neo",' +
    'system-ui,sans-serif;}' +
    '[font-family*="Mono"]{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace;}' +
    '</style>'
  // 여는 태그를 다시 찾는다 — 위에서 엔티티를 바꾸며 자리가 밀렸을 수 있다.
  const tag = svg.match(/<svg[^>]*>/)
  if (!tag) return svg
  const opened = tag[0].includes('xmlns')
    ? tag[0]
    : tag[0].replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  const at = (tag.index ?? 0) + tag[0].length
  return svg.slice(0, tag.index ?? 0) + opened + style + svg.slice(at)
}

/**
 * 같은 그림·같은 테마면 다시 안 받는다. 키에 테마를 넣어 색이 굳지 않게 한다.
 *
 * ## 누가 blob 을 쥐고 있나 — **캐시다**
 *
 * `URL.createObjectURL` 로 만든 주소는 해제하기 전까지 산다. 그 주소를 캐시가
 * 들고 있으므로 **쓰는 쪽(노드뷰)이 해제하면 안 된다** — 해제해도 캐시는 그
 * 문자열을 그대로 갖고 있어서, 다음에 **이미 죽은 주소**를 돌려준다.
 *
 * 실측(2026-08-29): 그림 자리에서 새로고침하면 보이는데 다른 화면에 갔다 오면
 * 안 보였다. 새로고침은 이 모듈까지 새로 만드니 다시 받았고, 화면만 옮기면
 * 노드뷰가 떠나며 해제한 주소를 캐시가 그대로 줬다.
 *
 * 그래서 **세션 동안 안 놓는다.** 그림 75개에 테마 둘이라도 몇 MB 다 — 죽은
 * 주소를 주는 것보다 낫다.
 */
const cache = new Map<string, Promise<string>>()

export function assetCacheKey(path: string, theme: AssetTheme): string {
  return `${path}|${theme.ink}|${theme.background}`
}

/**
 * 그림 하나를 blob 주소로. **실패하면 던진다** — 부르는 쪽이 「그림을 못 불러왔다」
 * 를 글로 보여 준다. 조용히 빈 자리를 두면 원래 그림이 없는 것과 구별이 안 된다.
 */
export function loadAsset(path: string, theme: AssetTheme): Promise<string> {
  const key = assetCacheKey(path, theme)
  const seen = cache.get(key)
  if (seen) return seen

  const pending = (async () => {
    const response = await fetchWithAuth(path)
    if (!response.ok) throw new Error(`그림을 못 불러왔습니다 (HTTP ${response.status})`)
    const type = response.headers.get('content-type') ?? ''
    if (type.includes('svg')) {
      const text = withTheme(await response.text(), theme)
      return URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }))
    }
    return URL.createObjectURL(await response.blob())
  })()

  // **실패는 캐시하지 않는다.** 잠깐 끊긴 것을 영영 기억하면 새로고침해야 낫는다.
  cache.set(key, pending)
  void pending.catch(() => cache.delete(key))
  return pending
}

/** 시험이 캐시를 비운다. 화면 코드에서는 안 쓴다. */
export function clearAssetCache(): void {
  cache.clear()
}
