/**
 * 적용 부품 붙여넣기 — **엑셀에서 복사한 BOM 범위를 줄로**(ADR 0064).
 *
 * BOM 은 사업부 · 양식마다 열 차례가 다르다. 열 이름으로 어느 칸인지 **짐작하되 화면에 보이고
 * 사람이 고친다** — 짐작이 조용히 틀리면 품번이 파트명 칸에 들어간 줄 수백 개가 남는다(BOM 덱이
 * 열을 사람에게 고르게 하는 것과 같은 판단).
 *
 * **탭으로만 나눈다.** 엑셀에서 복사하면 탭이 온다. 쉼표로 나누면 「도어 이너, 아우터」 같은
 * 파트명이 두 칸으로 갈라진다.
 */

import type {
  BomPartImport,
  MaterialPart,
  MaterialPartLine,
  MaterialPartUpdate,
} from '@/modules/materials/api'

export type PartField = 'material' | 'part' | 'product' | 'part_code' | 'division' | 'note'

export interface PartFieldSpec {
  key: PartField
  label: string
  /** 머리글로 알아보는 이름 — 비교는 소문자 · 공백과 기호를 뺀 글자로. */
  names: string[]
}

/** 고를 수 있는 칸. `material` 은 BOM 가져오기에만 있다(재료 화면에서는 재료가 정해져 있다). */
export const PART_FIELDS: PartFieldSpec[] = [
  { key: 'material', label: '재질', names: ['재질', '재료', '소재', 'material', 'grade', '강종'] },
  {
    key: 'part',
    label: '파트명',
    names: ['파트명', '파트', '부품명', '품명', 'part', 'partname', 'description', '부위'],
  },
  { key: 'product', label: '제품', names: ['제품', '제품명', '모델', '차종', 'product', 'model'] },
  {
    key: 'part_code',
    label: '부품코드',
    names: ['부품코드', '품번', '부품번호', '파트번호', 'partno', 'partnumber', 'pn', 'code'],
  },
  { key: 'division', label: '사업부', names: ['사업부', '부문', 'division', 'bu'] },
  { key: 'note', label: '비고', names: ['비고', '메모', 'note', 'remark', 'remarks'] },
]

/** 한 줄 = 칸들. 다 빈 줄은 뺀다. */
export function parseCells(text: string): string[][] {
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => line.split('\t').map((cell) => cell.trim()))
    .filter((cells) => cells.some((cell) => cell !== ''))
}

function squash(text: string): string {
  return text.toLowerCase().replace(/[\s_\-./()[\]#:]/g, '')
}

function fieldOf(cell: string, fields: PartFieldSpec[]): PartField | null {
  const key = squash(cell)
  if (!key) return null
  return fields.find((one) => one.names.includes(key))?.key ?? null
}

/** 첫 줄이 머리글인가 — 아는 열 이름이 하나라도 있으면 그렇다고 본다(사람이 끌 수 있다). */
export function looksLikeHeader(first: string[] | undefined, fields = PART_FIELDS): boolean {
  return (first ?? []).some((cell) => fieldOf(cell, fields) !== null)
}

/**
 * 열마다 어느 칸인지 짐작한다. 머리글이 없으면 `fallback` 차례로 채운다.
 *
 * **한 칸은 한 열에만** — 「품명」 과 「부품명」 이 둘 다 있으면 앞의 것만 파트명이다. 둘 다
 * 파트명이면 뒤 열이 앞 열을 조용히 덮는다.
 */
export function guessColumns(
  header: string[] | null,
  width: number,
  fields = PART_FIELDS,
  fallback: PartField[] = fields.map((one) => one.key)
): (PartField | null)[] {
  const out: (PartField | null)[] = Array.from({ length: width }, () => null)
  const taken = new Set<PartField>()
  if (header) {
    header.slice(0, width).forEach((cell, index) => {
      const found = fieldOf(cell, fields)
      if (found && !taken.has(found)) {
        out[index] = found
        taken.add(found)
      }
    })
    return out
  }
  fallback.slice(0, width).forEach((key, index) => {
    out[index] = key
  })
  return out
}

export type PartRecord = Partial<Record<PartField, string>>

/** 칸 → 줄. 고른 칸이 없는 열은 버린다. 빈 칸은 안 싣는다(서버가 「없음」 으로 읽는다). */
export function toRecords(cells: string[][], columns: (PartField | null)[]): PartRecord[] {
  return cells.map((row) => {
    const record: PartRecord = {}
    columns.forEach((key, index) => {
      const value = row[index]?.trim()
      if (key && value) record[key] = value
    })
    return record
  })
}

/** 붙여넣은 줄 → 서버가 보는 줄. 사업부 칸이 빈 줄에는 `division` 을 채운다. */
export function linesOf(records: PartRecord[], division: string): MaterialPartLine[] {
  return records.map((one) => ({
    part: one.part ?? null,
    product: one.product ?? null,
    part_code: one.part_code ?? null,
    division: one.division ?? (division.trim() || null),
    note: one.note ?? null,
  }))
}

/** 줄이 어디서 왔나. `legacy` 는 예전 칩에서 옮겨 온 줄이다(제품 · 파트의 짝을 모른다). */
export const SOURCE_LABELS: Record<string, string> = {
  manual: '직접 입력',
  bom: 'BOM',
  legacy: '예전 입력',
}

export type LineForm = Record<'part' | 'product' | 'part_code' | 'division' | 'note', string>

export function formOf(row: MaterialPart | null): LineForm {
  return {
    part: row?.part ?? '',
    product: row?.product ?? '',
    part_code: row?.part_code ?? '',
    division: row?.division ?? '',
    note: row?.note ?? '',
  }
}

/**
 * 고친 칸만 — **안 보낸 것과 비운 것을 가른다**(AGENTS). 다 보내면 그 사이 다른 사람이 고친
 * 칸을 이 창이 연 때의 값으로 되돌린다.
 */
export function changesOf(row: MaterialPart, form: LineForm): MaterialPartUpdate {
  const before = formOf(row)
  const out: MaterialPartUpdate = {}
  for (const key of Object.keys(form) as (keyof LineForm)[]) {
    const next = form[key].trim()
    if (next !== before[key].trim()) out[key] = next || null
  }
  return out
}

// ── BOM 가져오기 ─────────────────────────────────────────────────────────────

export const BOM_STATUS_LABELS: Record<string, string> = {
  new: '새로',
  exists: '이미 있음',
  unmatched: '재료 못 찾음',
  ambiguous: '재료 여럿',
  blocked: '고칠 권한 없음',
  error: '못 넣음',
}

export interface MaterialChoice {
  id: string
  name: string
}

/** 사람이 골라야 하는 재질 하나. */
export interface MaterialAsk {
  material: string
  status: 'unmatched' | 'ambiguous'
  /** 그 재질의 줄 수. */
  count: number
  candidates: MaterialChoice[]
}

/** 사람이 골라야 하는 재질 — 재질 글자마다 한 번(같은 재질 줄이 백 개여도 한 번 고른다). */
export function pending(result: BomPartImport | null): MaterialAsk[] {
  const found = new Map<string, MaterialAsk>()
  for (const row of result?.rows ?? []) {
    if ((row.status !== 'unmatched' && row.status !== 'ambiguous') || !row.material) continue
    const key = row.material.trim().toLowerCase()
    const seen = found.get(key)
    if (seen) seen.count += 1
    else
      found.set(key, {
        material: row.material,
        status: row.status,
        count: 1,
        candidates: (row.candidates ?? []).map((one) => ({ id: one.id, name: one.name })),
      })
  }
  return [...found.values()]
}

/** 앞에서 물은 재질은 그대로 두고 새로 물을 것만 덧붙인다. */
export function merge(before: MaterialAsk[], now: MaterialAsk[]): MaterialAsk[] {
  const seen = new Set(before.map((one) => one.material.trim().toLowerCase()))
  return [...before, ...now.filter((one) => !seen.has(one.material.trim().toLowerCase()))]
}
