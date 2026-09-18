/**
 * 단축키 — **입력 칸에서는 안 듣는다.**
 *
 * 검색 칸에 「f」 를 치는데 화면이 맞춰지면 그것은 기능이 아니라 버그다. 포커스가
 * input·textarea·contenteditable 에 있으면 전부 흘려보낸다. 단, ESC 만은 입력
 * 칸에서도 듣는다 — 검색을 치다가 빠져나오는 길이 그것이다.
 *
 * 키 이름은 `event.key` 그대로다. 조합은 `shift+Enter` 처럼 `shift+` 접두사만 둔다 —
 * Ctrl/Meta 조합은 브라우저 것과 겹치므로 여기서 안 쓴다.
 */

import { useEffect } from 'react'

export type ShortcutMap = Record<string, (event: KeyboardEvent) => void>

function inEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

export function useShortcuts(map: ShortcutMap, enabled = true): void {
  useEffect(() => {
    if (!enabled) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return
      const key = `${event.shiftKey && event.key.length > 1 ? 'shift+' : ''}${event.key}`
      const handler = map[key]
      if (!handler) return
      if (event.key !== 'Escape' && inEditable(event.target)) return
      handler(event)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [map, enabled])
}
