/**
 * 밀어 넣기 표 ↔ 서버가 받는 줄 (ADR 0054). 화면 파일(`TaxonomyImportDialog`)은 컴포넌트만 둔다.
 */

import type { Taxonomy, TaxonomyImportRow } from '@/modules/catalog/taxonomyApi'
import type { Column } from '@/shared/components/PasteGrid'

/** 표의 열 — 앞 셋이 기본이다. 세 열만 복사해 붙여도 맞는 자리에 들어간다. */
export const COLUMNS: (Column & { field: keyof TaxonomyImportRow })[] = [
  { key: 'field', field: 'field', header: '분야', help: '이름 또는 키' },
  { key: 'group', field: 'group', header: '물성군', help: '이름 또는 키. 비우면 분야만 만듭니다' },
  {
    key: 'property',
    field: 'property',
    header: '물성',
    help: '키 · 이름 · 별칭이 정확히 맞아야 합니다. 비우면 빈 물성군',
  },
  {
    key: 'field_key',
    field: 'field_key',
    header: '분야 키',
    // 기본 분야(기계 · 열 …)는 키가 키 앞머리(mechanical …)라 다른 키를 주면 이름이 겹쳐 그 줄이
    // 걸린다 — 이름으로 찾게 비워 두는 것이 맞다.
    help: '선택 — 주면 그 키로 찾고, 없으면 그 키로 만듭니다. 기본 분야는 이름으로 찾으니 비워 두세요',
  },
  {
    key: 'group_key',
    field: 'group_key',
    header: '물성군 키',
    help: '선택 — 비우면 pg-0001 꼴로 지어 줍니다. 바깥 시스템의 키를 그대로 쓰면 두 시스템의 키가 같아집니다',
  },
  { key: 'field_description', field: 'field_description', header: '분야 설명' },
  { key: 'group_description', field: 'group_description', header: '물성군 설명' },
]

export const BLANK = () => COLUMNS.map(() => '')

/** 지금 분류를 표로 — 엑셀로 복사해 고친 뒤 다시 붙이는 왕복 길. */
export function rowsOf(tree: Taxonomy): string[][] {
  const members = new Map<string, string[]>()
  for (const property of tree.properties) {
    if (property.group_key) {
      members.set(property.group_key, [...(members.get(property.group_key) ?? []), property.key])
    }
  }
  const rows: string[][] = []
  const order = [...tree.fields].sort((a, b) => a.sort_order - b.sort_order)
  for (const field of order) {
    if (field.retired) continue
    for (const group of tree.groups.filter((one) => one.field_key === field.key && !one.retired)) {
      const inside = members.get(group.key) ?? []
      // 빈 군도 한 줄 — 안 적으면 왕복하는 동안 사라진 것처럼 보인다.
      for (const property of inside.length ? inside : ['']) {
        rows.push([field.name, group.name, property, field.key, group.key, '', ''])
      }
    }
  }
  return rows
}

/** 표를 서버가 받는 줄로. **마지막 빈 줄만 뗀다** — 중간의 빈 줄은 줄 번호를 위해 남긴다. */
export function payloadOf(rows: string[][]): TaxonomyImportRow[] {
  let last = rows.length - 1
  while (last >= 0 && !rows[last].some((cell) => cell.trim())) last -= 1
  return rows.slice(0, last + 1).map((row) => {
    const one: TaxonomyImportRow = {}
    COLUMNS.forEach((column, at) => {
      const value = (row[at] ?? '').trim()
      if (value) one[column.field] = value
    })
    return one
  })
}
