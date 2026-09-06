/**
 * 덱 정의를 **물성 묶음**으로 접는다 — 저장 형식은 그대로 줄이다.
 *
 * 편집기가 줄을 평면으로 쌓게 하니 사람은 덱 문법과 카드 값 이름을 동시에 알아야 했다
 * (2026-09-05). 솔버 덱은 실제로 「키워드 한 줄 + 그 아래 값·표 줄」 의 반복이라, 그
 * 단위로 보이면 「탄성 묶음 · 밀도 묶음 · 소성 묶음」 이 된다.
 *
 * ## 접는 규칙
 *
 *   글자 줄            새 묶음의 머리(키워드)
 *   묶음(block) 줄      제 혼자 한 묶음 — 코드가 통째로 만든다
 *   값·표·plain 줄      바로 앞 머리에 딸린다. 머리 없이 시작하면 머리 없는 묶음
 *
 * `plain` 글자 줄(옵션 숫자·플래그)은 렌더러에게 키워드와 같은 글자 줄이지만, 여기서는
 * 몸에 붙는다 — 그것이 새 묶음을 열면 `*MAT` 아래 `1, 0, 0` 이 딴 묶음이 된다.
 *
 * ## 조건은 묶음에 한 번
 *
 * `when` 은 렌더러가 줄마다 본다. 묶음의 조건은 저장할 때 그 묶음의 모든 줄에 같은
 * 값으로 적히고, 읽을 때는 줄들의 `when` 이 모두 같으면 묶음 조건으로 접힌다. 다르면
 * 그대로 두고 「줄마다 다르다」 고 표시한다 — 정보를 잃지 않는다. `note` 는 렌더러가
 * 줄마다 한 번씩 쌓으므로 **머리(첫 줄)에만** 적는다.
 */

import type { DeckLine } from '@/modules/fitting/deckLines'

export type Section = {
  /** 키워드 줄. 없으면 값·표만 있는 묶음(머리 없음). */
  keyword: DeckLine | null
  /** 값·표·코드 묶음 줄. */
  body: DeckLine[]
  /** 묶음 전체의 조건. `mixedWhen` 이면 줄마다 다른 것을 그대로 두고 있다. */
  when: string
  mixedWhen: boolean
  note: string
}

function linesOf(section: Section): DeckLine[] {
  return section.keyword ? [section.keyword, ...section.body] : section.body
}

export function toSections(lines: DeckLine[]): Section[] {
  const sections: Section[] = []
  let current: Section | null = null
  const close = () => {
    if (!current) return
    const all = linesOf(current)
    const whens = all.map((one) => one.when ?? '')
    const same = whens.every((one) => one === whens[0])
    current.when = same ? (whens[0] ?? '') : ''
    current.mixedWhen = !same
    current.note = all[0]?.note ?? ''
    sections.push(current)
    current = null
  }
  for (const line of lines) {
    if (line.kind === 'text') {
      close()
      current = { keyword: line, body: [], when: '', mixedWhen: false, note: '' }
      continue
    }
    if (line.kind === 'block') {
      close()
      current = { keyword: null, body: [line], when: '', mixedWhen: false, note: '' }
      close()
      continue
    }
    if (!current) current = { keyword: null, body: [], when: '', mixedWhen: false, note: '' }
    current.body.push(line)
  }
  close()
  return sections
}

export function fromSections(sections: Section[]): DeckLine[] {
  const out: DeckLine[] = []
  for (const section of sections) {
    linesOf(section).forEach((line, at) => {
      const next: DeckLine = { ...line }
      if (!section.mixedWhen) {
        if (section.when) next.when = section.when
        else delete next.when
      }
      if (at === 0) {
        if (section.note) next.note = section.note
        else delete next.note
      } else {
        delete next.note
      }
      out.push(next)
    })
  }
  return out
}

/** 묶음 하나가 정의의 몇 번째 줄들인가 — 미리보기의 줄 구간과 잇는다. */
export function lineRanges(sections: Section[]): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = []
  let at = 0
  for (const section of sections) {
    const count = linesOf(section).length
    ranges.push({ start: at, end: at + count })
    at += count
  }
  return ranges
}

/** 머리글에 적는 요약: 「값 2 · 표 1」. */
export function summarize(section: Section): string {
  const fields = section.body.filter((one) => one.kind === 'fields').length
  const rows = section.body.filter((one) => one.kind === 'rows').length
  const plain = section.body.filter((one) => one.kind === 'plain').length
  const blocks = section.body.filter((one) => one.kind === 'block').length
  return [
    fields > 0 ? `값 줄 ${fields}` : '',
    rows > 0 ? `표 ${rows}` : '',
    plain > 0 ? `글자 줄 ${plain}` : '',
    blocks > 0 ? '코드 묶음' : '',
  ]
    .filter(Boolean)
    .join(' · ')
}
