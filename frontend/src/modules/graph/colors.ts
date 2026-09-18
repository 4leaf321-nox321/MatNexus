/**
 * 그래프의 색 — **같은 타입은 어디서나 같은 색.**
 *
 * 화면마다 색을 고르면 같은 「부품」 이 구조 그림에서는 파랑이고 탐색 그림에서는
 * 초록이 된다. 색은 slug 의 **순서**로 정한다(정의 순서). 해시로 정하면 타입이
 * 셋뿐인데 셋이 비슷한 색을 뽑는 날이 온다.
 */

/** 라이트·다크 둘 다에서 서로 구별되는 열두 색(Tailwind 500 계열). */
const PALETTE = [
  '#6366f1', // indigo
  '#10b981', // emerald
  '#f59e0b', // amber
  '#f43f5e', // rose
  '#0ea5e9', // sky
  '#8b5cf6', // violet
  '#14b8a6', // teal
  '#f97316', // orange
  '#84cc16', // lime
  '#d946ef', // fuchsia
  '#06b6d4', // cyan
  '#ef4444', // red
]

/** 열두 색이 다 나가면 회색 — **더 만들지 않는다.** 열셋째부터는 색으로 구별이 안 된다. */
export const OVERFLOW_COLOR = '#9ca3af'

export function colorScale(keys: string[]): (key: string) => string {
  const index = new Map(keys.map((key, i) => [key, i]))
  return (key) => {
    const i = index.get(key)
    if (i === undefined || i >= PALETTE.length) return OVERFLOW_COLOR
    return PALETTE[i]
  }
}

/** `#rrggbb` → `rgba()`. 외곽선·채움의 투명도를 따로 주려고 색 자체에 알파를 싣는다. */
export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}
