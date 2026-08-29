/**
 * 그림 노드 — **본문의 주소를 그대로 `<img>` 에 넣지 않는다.**
 *
 * 본문에는 `/api/guide/assets/<id>` 가 들어 있고 그것이 옳다(주소가 정본이다).
 * 다만 브라우저가 그 주소를 직접 열면 토큰이 안 실려 401 이 난다. 그래서 그리는
 * 순간에만 **토큰으로 받아 만든 blob 주소**로 바꿔 끼운다 — 저장되는 값은 안 바뀐다.
 *
 * 왜 노드뷰인가: 화면이 그린 `<img>` 의 `src` 를 나중에 손으로 고치면 ProseMirror 가
 * 다시 그릴 때 원래대로 돌아온다. **그리는 주체가 바꿔야** 한다.
 */

import Image from '@tiptap/extension-image'

import { ASSET_PREFIX, loadAsset, themeOf } from '@/modules/guide/assets'
import type { AssetTheme } from '@/modules/guide/assets'

/** 살아 있는 노드뷰들. 테마가 바뀌면 전부 다시 받는다. */
const alive = new Set<() => void>()

let watching = false

/**
 * 테마 토글을 지켜본다. **`prefers-color-scheme` 로는 안 된다** — 이 앱의 다크
 * 모드는 사람이 누르는 토글이라 OS 설정과 다를 수 있다(`ThemeProvider` 가
 * `<html>` 에 `dark` 를 붙였다 뗀다).
 */
function watchTheme() {
  if (watching || typeof MutationObserver === 'undefined') return
  watching = true
  new MutationObserver(() => {
    for (const redraw of alive) redraw()
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
}

export const AuthedImage = Image.extend({
  addNodeView() {
    return ({ node, HTMLAttributes }) => {
      const dom = document.createElement('img')
      for (const [key, value] of Object.entries(HTMLAttributes)) {
        if (value != null && key !== 'src') dom.setAttribute(key, String(value))
      }
      const src = String(node.attrs.src ?? '')
      if (!src.startsWith(ASSET_PREFIX)) {
        dom.src = src
        return { dom }
      }

      watchTheme()
      let theme: AssetTheme | null = null

      const draw = () => {
        const next = themeOf(dom.parentElement)
        if (theme && theme.ink === next.ink && theme.background === next.background) return
        theme = next
        void loadAsset(src, next)
          .then((url) => {
            // **여기서 앞의 주소를 놓지 않는다.** 캐시가 그 주소를 그대로 들고
            // 있어서, 놓으면 다음에 캐시가 **이미 해제된 주소**를 돌려준다
            // (`assets.ts` 의 「누가 blob 을 쥐고 있나」).
            dom.src = url
          })
          .catch((error: unknown) => {
            // **못 불러온 것을 빈자리로 두지 않는다.** 원래 그림이 없는 것과
            // 구별이 안 되고, 그러면 아무도 고장 났다고 말하지 않는다.
            dom.removeAttribute('src')
            dom.alt = `${node.attrs.alt ?? '그림'} — ${
              error instanceof Error ? error.message : '불러오지 못했습니다'
            }`
            dom.setAttribute('data-guide-asset-failed', 'true')
          })
      }

      draw()
      alive.add(draw)

      return {
        dom,
        destroy() {
          // **주소를 해제하지 않는다.** 화면을 떠났다 돌아오면 노드뷰가 다시
          // 만들어지는데, 캐시는 살아 있어서 같은 blob 주소를 돌려준다 — 떠날 때
          // 해제했다면 그것은 죽은 주소다.
          //
          // 실측(2026-08-29): 그 자리에서 새로고침하면 그림이 보이는데 다른 데
          // 갔다 오면 안 보였다. 새로고침은 모듈 캐시까지 비우니까 다시 받았고,
          // 화면만 옮기면 캐시가 죽은 주소를 그대로 줬다.
          alive.delete(draw)
        },
      }
    }
  },
})
