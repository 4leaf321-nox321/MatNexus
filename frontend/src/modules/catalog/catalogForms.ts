/**
 * 문헌 값을 넣는 창들이 함께 쓰는 고를 값 — 값 하나(`AddValueDialog`) · 곡선(`SeriesDialog`).
 * 서버 `contribute.METHODS` · `SOURCE_KINDS` 와 같다 — 두 창에 따로 적으면 한쪽만 고쳐진다.
 */

import type { CatalogValue } from '@/modules/catalog/api'

export const METHODS: [string, string][] = [
  ['handbook', '핸드북·규격'],
  ['measured', '실측(문서에 인쇄된)'],
  ['digitized', '그래프 판독'],
  ['computed', '계산'],
  ['estimated', '추정'],
]

export const SOURCE_KINDS: [string, string][] = [
  ['datasheet', '데이터시트'],
  ['journal', '논문'],
  ['book', '책·핸드북'],
  ['standard', '규격'],
  ['database', '데이터베이스'],
  ['web', '웹'],
  ['other', '기타'],
]

/** 방법의 짧은 이름 — 표 · 배지용. */
export const METHOD_LABELS: Record<string, string> = {
  measured: '실측',
  handbook: '핸드북',
  digitized: '그래프 판독',
  computed: '계산',
  estimated: '추정',
}

/** tier 4 에 가정 표지가 붙은 값 — 배지가 「가정」 으로 선다. */
export function isAssumed(value: CatalogValue): boolean {
  return value.quality_tier === 4 && value.conditions?.['assumption'] === true
}

/** 근거 없는 방법 — tier 4 여야 서버가 받는다. */
export const UNGROUNDED = new Set(['computed', 'estimated'])

export const SELECT = 'border-input bg-background h-9 w-full rounded-md border px-2 text-sm'

/**
 * 엑셀에서 복사한 표를 줄 · 칸으로 — 탭 · 쉼표 · 공백으로 가른다. 수가 아닌 첫 줄은 머리로
 * 보고 건너뛴다. 빈 칸 · `-` 는 null(그 열의 값이 없는 줄).
 */
export function parseRows(text: string): (number | null)[][] {
  const rows: (number | null)[][] = []
  for (const raw of text.split(/\r?\n/)) {
    // **줄 끝의 탭은 칸이다** — 엑셀은 끝 열이 빈 줄을 `100\t` 로 복사한다. 다듬으면 그 칸이
    // 사라져 서버가 「칸이 모자랍니다」 로 거절한다.
    if (!raw.trim()) continue
    const line = raw.includes('\t') ? raw.replace(/^ +| +$/g, '') : raw.trim()
    const cells = line.includes('\t') ? line.split('\t') : line.split(/[,;\s]+/)
    const parsed = cells.map((cell) => {
      const one = cell.trim().replace(/,/g, '')
      if (one === '' || one === '-') return null
      const number = Number(one)
      return Number.isFinite(number) ? number : Number.NaN
    })
    if (parsed.some((one) => one !== null && Number.isNaN(one))) {
      if (rows.length === 0) continue // 머리 줄
      throw new Error(`수가 아닌 칸이 있습니다: 「${line}」`)
    }
    rows.push(parsed as (number | null)[])
  }
  return rows
}

/** 「키=값」 을 쉼표 · 줄로 — 수로 읽히면 수로. 공통 조건 칸에 쓴다. */
export function parseConditions(text: string): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const part of text.split(/[\n,]+/)) {
    const [key, ...rest] = part.split('=')
    const name = key?.trim()
    const value = rest.join('=').trim()
    if (!name || !value) continue
    const number = Number(value)
    out[name] = Number.isFinite(number) ? number : value
  }
  return out
}
