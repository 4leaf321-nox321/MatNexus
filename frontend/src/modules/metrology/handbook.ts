/**
 * 측정법에서 **핸드북으로** — 그 물성 · 규격을 다룬 절을 찾을 말 (2026-10-03).
 *
 * 규격이 먼저다. 「ISO 6892」 가 나오는 절은 거의 틀림없이 그 시험법을 다루지만, 「밀도」 는
 * 「에너지 밀도」 에도 걸린다(실측: 핸드북 218절 중 37절). 그래서 규격으로 찾은 절을 앞에,
 * 이름으로 찾은 절을 뒤에 세운다.
 *
 * ## 규격 칸은 그대로 못 찾는다
 *
 * 장비 능력의 규격 칸은 원본(MaterialTwin) 글 그대로다 — 「JIS B0601-2001 / JIS B0601-1994 /
 * … / ANSI / VDA」 · 「ISO 22412:2017」 · 「ISO 6892-1」. 이것을 통째로 찾으면 아무 절에도 안
 * 걸린다. 나누고, 연도 · 부 번호를 떼고(「ISO 6892-1」 을 찾으면 「ISO 6892」 만 적은 절을
 * 놓친다), 기관 이름만 있는 조각(「ANSI」)은 버린다 — 그것으로 찾으면 아무 절이나 걸린다.
 */

import type { MetrologyProperty } from '@/modules/metrology/api'

/** 규격 번호로 알아보는 기관 — 이것으로 시작하고 번호가 붙은 조각만 규격으로 본다. */
const BODIES = /^(ISO|IEC|ASTM|JIS|DIN|EN|KS|BS|GB|ANSI|SAE|UL)\s*[A-Z]?\s*\d/i

/** 규격 칸의 글 → 핸드북에서 찾을 규격 번호들. 「ISO 22412:2017」 → 「ISO 22412」. */
export function standardCodes(raw: string | null | undefined): string[] {
  if (!raw) return []
  const codes: string[] = []
  for (const piece of raw.split(/[/,;]/)) {
    let code = piece.trim().replace(/\s+/g, ' ')
    // 연도(:2017 · -2001)와 부 번호(-1)를 뗀다 — 본문은 대개 기본 번호로 적는다.
    while (/[-:]\s*\d+$/.test(code) && BODIES.test(code.replace(/[-:]\s*\d+$/, ''))) {
      code = code.replace(/[-:]\s*\d+$/, '').trim()
    }
    if (!BODIES.test(code)) continue
    codes.push(code)
    // 「ASTM D 2240」 은 본문에 「ASTM D2240」 으로도 적힌다 — 둘 다 찾는다.
    const tight = code.replace(/^([A-Za-z]+ [A-Za-z]) (\d)/, '$1$2')
    if (tight !== code) codes.push(tight)
  }
  return [...new Set(codes)]
}

/** 찾을 말 — 규격 먼저(자주 나온 것부터), 그다음 물성 이름. 요청 수를 막으려 `limit` 개까지. */
export function handbookTerms(
  detail: MetrologyProperty,
  limit = 6
): { term: string; kind: 'standard' | 'name' }[] {
  const counted = new Map<string, number>()
  const raws = [
    detail.test_standard,
    ...detail.techniques.flatMap((group) => group.capabilities.map((one) => one.standard)),
  ]
  for (const raw of raws) {
    for (const code of standardCodes(raw)) counted.set(code, (counted.get(code) ?? 0) + 1)
  }
  const standards = [...counted.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([term]) => ({ term, kind: 'standard' as const }))
  const name = detail.name.trim()
  const terms = standards.slice(0, name.length >= 2 ? limit - 1 : limit)
  return name.length >= 2 ? [...terms, { term: name, kind: 'name' as const }] : terms
}
