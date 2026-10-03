/**
 * 절에 나오는 물성 — **핸드북에서 측정법으로** (2026-10-03).
 *
 * 절을 읽다가 「이 물성은 어느 장비 · 규격으로 재나」 로 넘어가는 길이다(MaterialTwin 이식
 * 4단계의 「안내서와 상호 링크」). 절에는 물성 키가 없어서 **이름이 본문에 나오는지**로 찾는다.
 * 길잡이지 판정이 아니다 — 잘못 걸려도 누르면 보이고, 아무것도 고치지 않는다.
 *
 *     두 글자 미만 이름은 안 본다     「E」 · 「ρ」 는 어디에나 있다
 *     더 긴 이름에 든 짧은 이름은 뺀다 「항복강도」 가 나왔는데 「강도」 까지 세우면 시끄럽다
 *     처음 나온 차례로                 절이 다루는 순서가 곧 읽는 순서다
 */

import type { Doc } from '@/modules/guide/api'
import type { MetrologyCoverageRow } from '@/modules/metrology/api'

/** 편집기 문서(ProseMirror JSON)의 글자만. 블록 사이는 줄을 바꾼다 — 낱말이 붙지 않게. */
export function textOf(doc: Doc): string {
  const parts: string[] = []
  const walk = (node: Record<string, unknown>) => {
    if (typeof node.text === 'string') parts.push(node.text)
    const children = node.content
    if (Array.isArray(children)) {
      for (const child of children) walk(child as Record<string, unknown>)
      parts.push('\n')
    }
  }
  walk(doc)
  return parts.join('')
}

/** 본문에 이름이 나오는 물성 — 처음 나온 차례로, 더 긴 이름에 든 짧은 이름은 빼고. */
export function mentionedProperties(
  text: string,
  rows: MetrologyCoverageRow[],
  limit = 8
): MetrologyCoverageRow[] {
  const haystack = text.toLowerCase()
  const found = rows
    .map((row) => ({ row, name: row.name.trim().toLowerCase() }))
    .filter((one) => one.name.length >= 2)
    .map((one) => ({ ...one, at: haystack.indexOf(one.name) }))
    .filter((one) => one.at >= 0)
  return found
    .filter((one) => !found.some((other) => other.name !== one.name && other.name.includes(one.name)))
    .sort((a, b) => a.at - b.at)
    .slice(0, limit)
    .map((one) => one.row)
}
