/**
 * 조사 — **「시험 를 담습니다」 를 안 쓴다.**
 *
 * 낱말을 표에서 읽어 문장을 만들면(`shared/units.ts` 도 그렇다) 조사가 따라 바뀐다.
 * 손으로 「을(를)」 이라고 적어 두는 길도 있지만, 그것이 열 군데 쌓이면 화면이 기계가
 * 쓴 것처럼 읽힌다. 받침만 보면 되는 일이라 여기서 한 번에 한다.
 *
 * 한글 음절은 `가`(0xAC00)부터 28개 종성이 한 묶음이다 — 나머지가 0이면 받침이 없다.
 * 한글이 아닌 글자(숫자·영문)로 끝나면 **아무 조사도 붙이지 않는다**: 「DMA를」 이
 * 맞는지 「DMA을」 이 맞는지는 읽는 법에 달렸고, 틀린 조사보다 없는 편이 낫다.
 */

/** 받침이 있나. 한글이 아니면 `null` — 「모른다」 와 「없다」 는 다르다. */
function hasFinal(word: string): boolean | null {
  const last = word.trim().at(-1)
  if (!last) return null
  const code = last.charCodeAt(0)
  if (code < 0xac00 || code > 0xd7a3) return null
  return (code - 0xac00) % 28 !== 0
}

const PAIRS = {
  '을/를': ['을', '를'],
  '이/가': ['이', '가'],
  '은/는': ['은', '는'],
  '과/와': ['과', '와'],
} as const

/**
 * 낱말에 조사를 붙인다. 「시험」 + `을/를` → 「시험을」, 「카드」 → 「카드를」.
 *
 * @param word 앞말
 * @param pair 어느 조사인가
 */
export function withJosa(word: string, pair: keyof typeof PAIRS): string {
  const final = hasFinal(word)
  if (final === null) return word
  const [withFinal, without] = PAIRS[pair]
  return `${word}${final ? withFinal : without}`
}
