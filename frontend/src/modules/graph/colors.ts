/**
 * 그래프의 색 — **같은 타입은 어디서나 같은 색.**
 *
 * 화면마다 색을 고르면 같은 「부품」 이 구조 그림에서는 파랑이고 탐색 그림에서는
 * 초록이 된다. 색은 slug 의 **순서**로 정한다(정의 순서). 해시로 정하면 타입이
 * 셋뿐인데 셋이 비슷한 색을 뽑는 날이 온다.
 *
 * ## 열셋째부터도 색이 있다 — 회색으로 떨어뜨리지 않는다 (2026-10-03)
 *
 * 전에는 고른 열두 색이 다 나가면 회색이었다(「열셋째부터는 색으로 구별이 안 된다」).
 * 그런데 지식 그래프의 마디 종류가 21개 · 관계가 26개라, 탐색을 넓히면 문헌 재료 ·
 * 출처 · 장비 · 용어 · 가이드 … 아홉 종류가 **같은 회색**이 됐다 — 「일정 이상
 * 늘어나니까 회색이 나온다」(사용자 지적). 같은 회색은 「구별 안 됨」 이 아니라 「같은 것」
 * 으로 읽힌다. 커뮤니티 색도 같은 함수를 써서 무리가 열둘을 넘으면 그랬다.
 *
 * 뒤에 붙인 서른여섯 색(`EXTENDED`)은 **앞의 색들에서 가장 먼 것을 하나씩 더해 간
 * 차례**다(CIEDE2000, 채도 높은 후보 가운데 밝은 바탕 #f8fafc 에서 대비 1.9 · 어두운
 * 바탕 #0b1220 에서 3.2 이상 — 고른 열두 색의 가장 낮은 대비 수준). 새 색은 어느 색과도
 * ΔE 12.8 넘게 떨어져 있어, 고른 열두 색 안의 가장 가까운 쌍(인디고 · 바이올렛 7.2)보다
 * 멀다. 처음에는 색상을 황금각으로 돌려 만들었는데, 재 보니 열넷째가 바이올렛과 거의
 * 같았다(ΔE 3.0) — 그래서 계산해 둔 차례를 적어 둔다.
 */

/** 라이트·다크 둘 다에서 서로 구별되는 열두 색(Tailwind 500 계열). **앞 열둘은 늘 이 차례다.** */
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

/** 열셋째부터 — 앞의 색들에서 가장 먼 것부터(위 설명). 지식 그래프의 마디 21종 · 관계 26종을 넉넉히 덮는다. */
const EXTENDED = [
  '#958923', '#955623', '#bb1b83', '#237895', '#4b9523', '#de73a8',
  '#d2b541', '#7393de', '#ad740b', '#de8873', '#bb331b', '#ad0dc9',
  '#c90d4f', '#238f95', '#1b6bbb', '#dea373', '#239578', '#1bbb3b',
  '#c9580d', '#f1228a', '#a0ae29', '#0f85e6', '#de7383', '#d241ae',
  '#bb931b', '#ae73de', '#de73d3', '#f15622', '#239550', '#7e9523',
  '#d6841f', '#6c3ff3', '#d61f3a', '#1b8bbb', '#64ad0b', '#0f5ae6',
]

const FIXED = [...PALETTE, ...EXTENDED]

/** 쉰째 너머(무리가 그만큼 많을 때) — 색상을 황금각으로 돌려 만든다. 채도 높게 · 가운데 명도. */
const GOLDEN_ANGLE = 137.508

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const a = saturation * Math.min(lightness, 1 - lightness)
  const channel = (n: number) => {
    const k = (n + hue / 30) % 12
    const value = lightness - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(value * 255)
      .toString(16)
      .padStart(2, '0')
  }
  return `#${channel(0)}${channel(8)}${channel(4)}`
}

/** `index` 번째 색. 앞 마흔여덟은 정해 둔 색, 그 뒤는 만든 색 — **끝이 없고 회색이 없다.** */
export function paletteColor(index: number): string {
  if (index < FIXED.length) return FIXED[index]
  const n = index - FIXED.length
  return hslToHex((n * GOLDEN_ANGLE) % 360, 0.8, n % 2 === 0 ? 0.48 : 0.56)
}

/** 목록에 없는 키 — 그래도 회색이 아니라, 이름에서 늘 같은 자리를 받는다. */
function hashIndex(key: string): number {
  let hash = 0
  for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  return hash % 360
}

export function colorScale(keys: string[]): (key: string) => string {
  const index = new Map(keys.map((key, i) => [key, i]))
  return (key) => {
    const i = index.get(key)
    // 목록에 없는 키는 목록 뒤에 — 목록의 색과 겹치지 않게.
    return paletteColor(i ?? keys.length + hashIndex(key))
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
