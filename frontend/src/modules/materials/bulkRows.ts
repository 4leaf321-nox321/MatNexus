/**
 * 재료·시료·시편을 **표 하나로** 받을 때 쓰는 규칙 — 칸 목록, 붙여 넣기,
 * 흠 짚기, 그리고 평평한 표를 나무로 묶기.
 *
 * ## 왜 표인가
 *
 * 처음에는 텍스트 상자 하나에 `Grade, 상세, 두께` 순으로 적게 했다. 그런데
 * **무엇을 어느 자리에 적어야 하는지가 화면에 없었다** — 설명 문장을 읽고
 * 순서를 외워서 적어야 했고, 칸을 하나 건너뛰려면 쉼표를 연달아 찍어야 했다.
 *
 * ## 왜 한 표에 셋을 다 두는가
 *
 * 판이 하나 들어오면 재료·시료·시편이 **같은 순간에 정해진다.** 창을 셋 거치게
 * 하면 그 사이에 하나를 빠뜨리고, 빠뜨린 것은 시험 파일이 도착할 때에야 보인다.
 *
 * 대신 칸이 스물 몇 개가 된다 — 그래서 **열마다 켜고 끈다.** 재료만 넣는 날은
 * 재료 칸만 보이면 된다.
 *
 * ## 빈 칸은 위와 같다
 *
 * 재료 칸이 빈 줄은 위 줄의 재료에 붙고, 시료 칸이 빈 줄은 위 줄의 시료에
 * 붙는다. 엑셀에서 늘 하는 방식이고, 덕분에 **한 재료 아래 시료 여럿, 한 시료
 * 아래 시편 여럿**이 표에서 그대로 읽힌다:
 *
 * ```
 * SECC MDOI 1.0 │ LOT-A │ MD 1
 *               │       │ MD 2
 *               │ LOT-B │ TD 1
 * ```
 *
 * ## 계산을 화면에서 뗀 이유
 *
 * 붙여 넣기·묶기·검사는 React 없이 시험할 수 있다. 표를 그리는 코드에 섞어
 * 두면 「탭으로 나누는가」를 확인하려고 창을 열어야 한다.
 */

import { DENSITY_UNIT, LENGTH_UNIT, ORIENTATIONS } from '@/modules/materials/api'
import { display } from '@/shared/units'
import type { BulkRequest } from '@/modules/materials/api'

/** 밀도를 보여 줄 기호. 보내는 것은 `DENSITY_UNIT`(위첨자 없는 표기)다. */
const DENSITY_SYMBOL = display('kg/m3').unit

export type Group = 'material' | 'sample' | 'specimen'

/** 표의 열 하나 — 재료·시료·시편의 칸 하나에 대응한다. */
export interface Column {
  /** 표 안에서만 쓰는 열쇠. 세 갈래에 같은 이름의 칸이 있어서 갈래를 붙인다. */
  key: string
  /** 요청 본문의 필드 이름. **화면이 이름을 새로 짓지 않는다.** */
  field: string
  group: Group
  label: string
  /** 단위처럼 머리글에 작게 붙는 것. */
  hint?: string
  kind: 'text' | 'number' | 'date'
  placeholder?: string
  /** 열 너비. 값이 짧은 칸에 넓은 자리를 주면 한 화면에 안 들어간다. */
  width: string
  /** 열자마자 보이는 칸인가. 스물 몇 개를 다 펼치면 아무것도 못 읽는다. */
  shown?: boolean
  /**
   * 비워 두면 **위 재료에서 이어받는** 칸.
   *
   * Grade 열에만 스무 줄을 붙여 넣는 것이 실제 작업이다. 그때 분류를 줄마다
   * 다시 적게 하면 **오타 하나가 분류를 갈라 놓고**, 그때 목록이 두 덩이로
   * 보인다. 이름을 만드는 값(Grade·Details·두께)은 이어받지 않는다 — 그것이
   * 이어지면 같은 재료가 두 줄이 된다.
   */
  carry?: boolean
  /**
   * 한 칸에 **여러 값**이 들어가는가. `;` 로 나눈다.
   *
   * 쉼표·탭은 이미 붙여 넣기가 칸을 가르는 데 쓴다 — 그것을 값 안에 두면
   * 엑셀에서 돌아온 표가 통째로 밀린다.
   */
  list?: boolean
}

const GROUP_LABELS: Record<Group, string> = {
  material: '재료',
  sample: '시료',
  specimen: '시편',
}

export function groupLabel(group: Group): string {
  return GROUP_LABELS[group]
}

/**
 * 표에 그릴 수 있는 칸 전부.
 *
 * 하나씩 등록하는 창들과 **같은 칸, 같은 순서**다. 두 길이 다른 칸을 받으면
 * 사람은 「여러 개로 넣으면 별칭을 못 넣는다」 같은 것을 겪고, 그것이 규칙인지
 * 빠뜨린 것인지 알 수 없다.
 */
export const COLUMNS: Column[] = [
  // --- 재료 ---
  {
    key: 'material.family',
    field: 'family',
    group: 'material',
    label: 'Family',
    kind: 'text',
    placeholder: 'Metal',
    width: 'w-24',
    shown: true,
    carry: true,
  },
  {
    key: 'material.category',
    field: 'category',
    group: 'material',
    label: 'Category',
    kind: 'text',
    placeholder: 'Steel',
    width: 'w-24',
    shown: true,
    carry: true,
  },
  {
    key: 'material.grade',
    field: 'grade',
    group: 'material',
    label: 'Grade',
    kind: 'text',
    placeholder: 'SECC',
    width: 'w-28',
    shown: true,
  },
  {
    key: 'material.details',
    field: 'details',
    group: 'material',
    label: 'Details',
    kind: 'text',
    placeholder: 'MDOI',
    width: 'w-24',
    shown: true,
  },
  {
    key: 'material.spec_thickness',
    field: 'spec_thickness',
    group: 'material',
    label: '두께',
    hint: 'mm',
    kind: 'number',
    placeholder: '1.0',
    width: 'w-20',
    shown: true,
  },
  {
    key: 'material.alias',
    field: 'alias',
    group: 'material',
    label: '별칭',
    kind: 'text',
    placeholder: '도어 이너',
    width: 'w-28',
    shown: true,
  },
  {
    key: 'material.applied_product',
    field: 'applied_products',
    group: 'material',
    label: '적용 제품',
    kind: 'text',
    width: 'w-24',
    carry: true,
    list: true,
    hint: '; 로 나눔',
  },
  {
    key: 'material.applied_part',
    field: 'applied_parts',
    group: 'material',
    label: '적용 부위',
    kind: 'text',
    width: 'w-24',
    carry: true,
    list: true,
    hint: '; 로 나눔',
  },
  {
    key: 'material.density',
    field: 'density',
    group: 'material',
    label: '밀도',
    hint: DENSITY_SYMBOL,
    kind: 'number',
    placeholder: '7.85e-9',
    width: 'w-24',
  },
  {
    key: 'material.poisson_ratio',
    field: 'poisson_ratio',
    group: 'material',
    label: '푸아송비',
    kind: 'number',
    placeholder: '0.3',
    width: 'w-20',
  },

  // --- 시료 ---
  {
    key: 'sample.lot_no',
    field: 'lot_no',
    group: 'sample',
    label: '로트번호',
    kind: 'text',
    placeholder: 'LOT-A',
    width: 'w-28',
    shown: true,
  },
  {
    key: 'sample.alias',
    field: 'alias',
    group: 'sample',
    label: '시료 별칭',
    kind: 'text',
    width: 'w-28',
  },
  {
    key: 'sample.manufacturer',
    field: 'manufacturer',
    group: 'sample',
    label: '제조사',
    kind: 'text',
    width: 'w-24',
    shown: true,
  },
  {
    key: 'sample.distributor',
    field: 'distributor',
    group: 'sample',
    label: '유통사',
    kind: 'text',
    width: 'w-24',
  },
  {
    key: 'sample.primary_vendor',
    field: 'primary_vendor',
    group: 'sample',
    label: '주 공급사',
    kind: 'text',
    width: 'w-24',
  },
  {
    key: 'sample.sales_type',
    field: 'sales_type',
    group: 'sample',
    label: '판매 구분',
    kind: 'text',
    width: 'w-24',
  },
  {
    key: 'sample.production_date',
    field: 'production_date',
    group: 'sample',
    label: '제조일',
    hint: 'YYYY-MM-DD',
    kind: 'date',
    placeholder: '2026-08-25',
    width: 'w-28',
    shown: true,
  },
  {
    key: 'sample.density',
    field: 'density',
    group: 'sample',
    label: '시료 밀도',
    hint: DENSITY_SYMBOL,
    kind: 'number',
    width: 'w-24',
  },

  // --- 시편 ---
  {
    key: 'specimen.orientation',
    field: 'orientation',
    group: 'specimen',
    label: '방향',
    kind: 'text',
    placeholder: 'MD',
    width: 'w-16',
    shown: true,
  },
  {
    key: 'specimen.seq_no',
    field: 'seq_no',
    group: 'specimen',
    label: '번호',
    kind: 'number',
    placeholder: '자동',
    width: 'w-16',
  },
  {
    key: 'specimen.standard',
    field: 'standard',
    group: 'specimen',
    label: '규격',
    kind: 'text',
    placeholder: 'KS B 0801',
    width: 'w-28',
    shown: true,
  },
  {
    key: 'specimen.thickness',
    field: 'thickness',
    group: 'specimen',
    label: '시편 두께',
    hint: 'mm',
    kind: 'number',
    width: 'w-24',
    shown: true,
  },
  {
    key: 'specimen.width',
    field: 'width',
    group: 'specimen',
    label: '폭',
    hint: 'mm',
    kind: 'number',
    width: 'w-20',
    shown: true,
  },
  {
    key: 'specimen.gauge_length',
    field: 'gauge_length',
    group: 'specimen',
    label: '게이지 길이',
    hint: 'mm',
    kind: 'number',
    width: 'w-24',
    shown: true,
  },
]

/** 표의 줄 하나. 값은 사람이 적은 그대로 문자열로 들고 있는다. */
export type Row = Record<string, string>

/** 처음에 그려 두는 빈 줄 수 — 표가 비어 있으면 어디에 적는지 알기 어렵다. */
export const EMPTY_ROWS = 5

/** 서버가 한 번에 받는 줄 수. 넘으면 서버가 422 로 막는다. */
export const MAX_ROWS = 2000

export function blankRow(): Row {
  return Object.fromEntries(COLUMNS.map((column) => [column.key, '']))
}

export function blankRows(count = EMPTY_ROWS): Row[] {
  return Array.from({ length: count }, blankRow)
}

/** 열자마자 켜져 있는 칸들. 재료만. */
export function initialShown(): Set<string> {
  return new Set(
    COLUMNS.filter((column) => column.group === 'material' && column.shown).map(
      (column) => column.key
    )
  )
}

/**
 * 비워 둔 「이어받는 칸」을 위 재료의 값으로 채운 표.
 *
 * **원본은 그대로 둔다** — 화면은 사람이 적은 것을 보여 주고, 이어받은 값은
 * 흐리게 비쳐 준다. 원본에 써 넣으면 위 줄을 고쳤을 때 아래가 따라오지 않는다.
 */
export function carried(rows: Row[], visible: Column[] = COLUMNS): Row[] {
  const keep: Record<string, string> = {}
  const carriers = visible.filter((column) => column.carry)
  return rows.map((row) => {
    // 재료 칸이 하나도 없는 줄은 새 재료가 아니다 — 채우면 없던 재료가 생긴다.
    if (!has(row, 'material', visible)) return row
    const next = { ...row }
    for (const column of carriers) {
      const text = (next[column.key] ?? '').trim()
      if (text) keep[column.key] = text
      else if (keep[column.key]) next[column.key] = keep[column.key]
    }
    return next
  })
}


function valuesIn(row: Row, columns: Column[]): string[] {
  return columns.map((column) => (row[column.key] ?? '').trim())
}

/** 이 갈래의 칸이 하나라도 채워져 있나. **묶는 규칙 전부가 여기에 달려 있다.** */
export function has(row: Row, group: Group, columns: Column[] = COLUMNS): boolean {
  return valuesIn(
    row,
    columns.filter((column) => column.group === group)
  ).some(Boolean)
}

export function isEmpty(row: Row, columns: Column[] = COLUMNS): boolean {
  return valuesIn(row, columns).every((value) => value === '')
}

/**
 * 붙여 넣은 것을 표에 **펼칠지** 아니면 글자 그대로 넣을지.
 *
 * 줄바꿈이나 탭이 있으면 여러 칸이다. 쉼표만 있는 한 줄은 **글자 그대로** 둔다 —
 * 별칭에 `도어 이너, 아우터` 를 붙여 넣었는데 두 칸으로 갈라지면 안 된다.
 */
export function spreads(text: string): boolean {
  return /[\t\n]/.test(text)
}

/**
 * 붙여 넣은 덩어리를 줄과 칸으로 나눈다.
 *
 * **엑셀에서 복사하면 탭이 온다.** 탭이 하나라도 있으면 탭으로 나눈다 — 그때
 * 쉼표는 값의 일부다(`1,000` 같은 것). 탭이 없으면 쉼표로 나눈다.
 */
export function parseGrid(text: string): string[][] {
  const separator = text.includes('\t') ? '\t' : ','
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .filter((line) => line.trim() !== '')
    .map((line) => line.split(separator).map((cell) => cell.trim()))
}

/**
 * 붙여 넣은 것을 `atRow`·`atColumn` 부터 채운다. `visible` 은 **지금 보이는
 * 열**이다 — 안 보이는 칸으로 값이 새면 사람은 그것을 영영 못 본다.
 *
 * 줄이 모자라면 늘린다 — **20줄을 붙여 넣었는데 5줄만 들어가면**, 사람은 나머지
 * 15줄이 어디로 갔는지 모른 채 만들기를 누른다.
 */
export function paste(
  rows: Row[],
  text: string,
  atRow: number,
  atColumn: number,
  visible: Column[]
): Row[] {
  const grid = parseGrid(text)
  const next = rows.map((row) => ({ ...row }))
  while (next.length < atRow + grid.length) next.push(blankRow())

  grid.forEach((cells, down) => {
    cells.forEach((cell, across) => {
      const column = visible[atColumn + across]
      // 표보다 넓게 붙여 넣으면 넘치는 칸은 버린다. 다음 줄로 밀면 값이
      // 엉뚱한 칸에 들어가고, 그 편이 훨씬 알아채기 어렵다.
      if (column) next[atRow + down][column.key] = cell
    })
  })
  return next
}

/**
 * 표를 **엑셀에 붙일 수 있는 글자**로. 첫 줄은 머리글이다.
 *
 * ## 왜 머리글이 반드시 들어가는가
 *
 * 붙여 넣은 사람이 엑셀에서 그 시트를 이어 쓴다. 머리글이 없으면 어느 열이
 * 무엇인지 그 자리에서 다시 세어야 하고, **한 칸 밀린 것을 알아채지 못한 채**
 * 표로 되돌려 붙인다. 그때 두께 자리에 별칭이 들어간다.
 *
 * ## 왜 탭인가
 *
 * 붙여 넣기가 탭을 먼저 본다(`parseGrid`). 같은 글자를 복사해 되돌려 붙이면
 * 그대로 돌아온다 — 쉼표로 내보내면 `1,000` 같은 값이 두 칸으로 갈라진다.
 *
 * ## 보이는 열만
 *
 * 안 보이는 칸까지 내보내면 엑셀의 열 수와 화면의 열 수가 달라지고, 되돌려
 * 붙일 때 어긋난다. **화면에 있는 표를 그대로 옮긴다.**
 */
export function toTsv(rows: Row[], visible: Column[] = COLUMNS): string {
  const head = visible.map((column) =>
    column.hint ? `${column.label} (${column.hint})` : column.label
  )
  const body = rows
    .filter((row) => !isEmpty(row, visible))
    .map((row) =>
      visible.map((column) => (row[column.key] ?? '').trim().replace(/[\t\n]/g, ' '))
    )
  // 적은 줄이 없어도 머리글은 나간다 — **엑셀에서 먼저 채우고 돌아오는 것**이
  // 이 기능의 쓰임 절반이다.
  return [head, ...body].map((cells) => cells.join('\t')).join('\n')
}


/** 서버가 이름을 만드는 값들 — 같은 이름이 될 줄을 알아보려고 쓴다. */
function nameKey(row: Row): string {
  return ['material.grade', 'material.details', 'material.spec_thickness']
    .map((key) => (row[key] ?? '').trim().toLowerCase())
    .join(' ')
}

/** 줄 번호 → 칸 열쇠 → 무엇이 잘못됐는지. */
export type Problems = Record<number, Record<string, string>>

function numberProblem(column: Column, text: string): string | undefined {
  const value = Number(text)
  if (!Number.isFinite(value)) return '숫자가 아닙니다'
  if (column.key === 'material.poisson_ratio') {
    // 서버와 같은 범위다(0 이상 0.5 미만). 0.5 는 완전 비압축이라 풀리지 않는다.
    return value < 0 || value >= 0.5 ? '0 이상 0.5 미만' : undefined
  }
  if (column.key === 'specimen.seq_no') {
    return Number.isInteger(value) && value >= 1 ? undefined : '1 이상의 정수'
  }
  return value <= 0 ? '0 보다 커야 합니다' : undefined
}

/**
 * 보내기 전에 짚을 수 있는 것만 짚는다.
 *
 * 서버가 다시 검사한다 — 여기서 걸러 내는 것은 **어느 줄이 문제인지 말해 주기
 * 위해서**다. 스무 줄을 보내고 「422」 하나를 받으면 어느 줄인지 모른다.
 */
export function problems(rows: Row[], visible: Column[] = COLUMNS): Problems {
  const found: Problems = {}
  const note = (at: number, key: string, why: string) => {
    found[at] = { ...found[at], [key]: why }
  }
  /** 이름 → 그 이름을 처음 쓴 줄. */
  const seen = new Map<string, number>()
  let openMaterial = -1

  rows.forEach((row, at) => {
    if (isEmpty(row, visible)) return
    const material = has(row, 'material', visible)

    if (material) {
      if (!(row['material.grade'] ?? '').trim()) note(at, 'material.grade', 'Grade 가 필요합니다')
      if (!(row['material.family'] ?? '').trim())
        note(at, 'material.family', 'Family 가 필요합니다')
      if (!(row['material.category'] ?? '').trim())
        note(at, 'material.category', 'Category 가 필요합니다')
      openMaterial = at
    } else if (openMaterial < 0) {
      // 첫 줄이 시료·시편만 적혀 있으면 붙일 재료가 없다.
      note(at, visible[0]?.key ?? 'material.grade', '위에 재료가 있어야 합니다')
    }

    for (const column of visible) {
      const text = (row[column.key] ?? '').trim()
      if (text === '') continue
      if (column.kind === 'number') {
        const why = numberProblem(column, text)
        if (why) note(at, column.key, why)
      } else if (column.kind === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(text)) {
        note(at, column.key, 'YYYY-MM-DD 로 적으세요')
      } else if (
        column.key === 'specimen.orientation' &&
        !ORIENTATIONS.includes(text.toUpperCase() as (typeof ORIENTATIONS)[number])
      ) {
        note(at, column.key, `${ORIENTATIONS.join(' · ')} 중 하나`)
      }
    }

    // **같은 이름이 될 줄을 미리 짚는다** — 딸린 것이 없을 때만. 시료·시편이
    // 붙어 있으면 그것은 「같은 재료 아래에 더 넣는다」는 뜻이고, 서버도 그렇게
    // 받는다. 그 경우까지 빨갛게 칠하면 이 표의 쓰임 자체가 막힌다.
    if (!material) return
    const key = nameKey(row)
    const earlier = seen.get(key)
    const alone = !has(row, 'sample', visible) && !has(row, 'specimen', visible)
    if (earlier !== undefined && alone) {
      note(at, 'material.grade', `${earlier + 1}번 줄과 같은 이름이 됩니다`)
    } else if (earlier === undefined) {
      seen.set(key, at)
    }
  })

  return found
}

// --- 평평한 표를 나무로 -----------------------------------------------------

type MaterialNode = BulkRequest['materials'][number]
type SampleNode = NonNullable<MaterialNode['samples']>[number]
type SpecimenNode = NonNullable<SampleNode['specimens']>[number]

/**
 * 이 갈래의 값들. **빈 칸은 안 보낸다** — 빈 문자열을 보내면 `''` 가 저장되고,
 * 나중에 「비었나」 를 물을 수 없다.
 */
function values(
  row: Row,
  target: Group,
  visible: Column[]
): Record<string, string | number | string[]> {
  const out: Record<string, string | number | string[]> = {}
  for (const column of visible) {
    if (column.group !== target) continue
    const text = (row[column.key] ?? '').trim()
    if (text === '') continue
    if (column.list) {
      const many = text
        .split(';')
        .map((one) => one.trim())
        .filter(Boolean)
      // 세미콜론만 적힌 칸은 **안 보낸다.** 빈 목록을 보내면 「다 지운다」 는
      // 뜻이 되는데, 그건 사람이 의도한 것이 아니다.
      if (many.length > 0) out[column.field] = many
      continue
    }
    out[column.field] = column.kind === 'number' ? Number(text) : text
  }
  return out
}

/** 표의 칸에서 값 하나. 없으면 빈 문자열 — 없는 것은 `problems` 가 짚는다. */
function cell(row: Row, key: string): string {
  return (row[key] ?? '').trim()
}

function materialNode(row: Row, at: number, visible: Column[]): MaterialNode {
  // 나머지 칸은 열 목록이 정하므로 이름을 미리 알 수 없다. 반드시 있어야 하는
  // 것들은 아래에서 다시 적어 덮는다.
  const rest = values(row, 'material', visible) as Partial<MaterialNode>
  return {
    ...rest,
    family: cell(row, 'material.family'),
    category: cell(row, 'material.category'),
    grade: cell(row, 'material.grade'),
    // **단위는 값과 함께 항상 명시한다.** 생략하면 "이 값이 mm 였나" 를
    // 나중에 아무도 답할 수 없다.
    spec_thickness_unit: LENGTH_UNIT,
    density_unit: DENSITY_UNIT,
    row: at,
    samples: [],
  }
}

function sampleNode(row: Row, at: number, visible: Column[]): SampleNode {
  const rest = values(row, 'sample', visible) as Partial<SampleNode>
  return { ...rest, density_unit: DENSITY_UNIT, row: at, specimens: [] }
}

function specimenNode(row: Row, at: number, visible: Column[]): SpecimenNode {
  const rest = values(row, 'specimen', visible) as Partial<SpecimenNode>
  return {
    ...rest,
    orientation: cell(row, 'specimen.orientation').toUpperCase() || 'NA',
    length_unit: LENGTH_UNIT,
    row: at,
  }
}

/** 몇 개가 만들어질지 — 보내기 전에 화면이 말해 준다. */
export interface Tally {
  materials: number
  samples: number
  specimens: number
  /** 시편만 적어서 저절로 생기는 시료 수. **말해 주지 않으면 놀란다.** */
  implied: number
}

/** 이 재료 마디의 **정체**. 이름을 만드는 값들이다(ADR 0004). */
function materialKey(node: MaterialNode): string {
  return [node.family, node.category, node.grade, node.details ?? '', node.spec_thickness ?? '']
    .map((one) => String(one ?? '').trim().toLowerCase())
    .join(' ')
}

/**
 * 평평한 표를 요청 본문으로 묶는다 — **「빈 칸은 위와 같다」가 사는 유일한 곳.**
 *
 * 서버가 이 규칙을 다시 해석하게 하면 규칙이 두 곳에 살고, 언젠가 갈라진다.
 *
 * ## 같은 것을 다시 적어도 하나다
 *
 * 「빈 칸은 위와 같다」 만으로는 모자랐다. **DB 를 뽑아 오면 모든 칸이 매 줄에
 * 차 있다** — 그게 덤프의 생김새다. 그때 이 함수가 줄마다 새 재료를 만들어서,
 * 시편 3장짜리 시료 하나가 **재료 3개·시료 3개·시편 3개**가 됐다(실사용에서
 * 나왔다).
 *
 * 그래서 **내용이 같으면 앞엣것에 붙인다.** 빈 칸을 세는 대신 정체를 본다.
 *
 * 시료는 **로트가 있을 때만** 그렇게 묶는다. 로트를 안 적은 시료 둘은 서로
 * 다른 시료일 수 있고, 그것을 합치면 사람이 적은 것과 다른 결과가 된다.
 */
export function group(rows: Row[], visible: Column[] = COLUMNS): BulkRequest {
  const materials: MaterialNode[] = []
  const seen = new Map<string, MaterialNode>()
  let material: MaterialNode | null = null
  let sample: SampleNode | null = null

  for (const [at, row] of rows.entries()) {
    if (isEmpty(row, visible)) continue

    if (has(row, 'material', visible)) {
      const made = materialNode(row, at, visible)
      const key = materialKey(made)
      const already = seen.get(key)
      if (already) {
        // 같은 재료를 다시 적었다. 새로 만들지 않고 그쪽에 붙인다.
        material = already
        // **그 재료의 마지막 시료를 이어받는다.** 여기서 `null` 로 두면, 시료를
        // 안 적은 줄이 시료를 새로 만든다 — 사이에 다른 재료가 껴 있었다는
        // 이유만으로 시료가 갈라지는 셈이다.
        const kin = already.samples as SampleNode[]
        sample = kin.length > 0 ? kin[kin.length - 1] : null
      } else {
        material = made
        materials.push(made)
        seen.set(key, made)
        sample = null
      }
    }
    if (material === null) continue // 붙일 재료가 없다 — `problems` 가 짚는다

    const samples = material.samples as SampleNode[]
    if (has(row, 'sample', visible)) {
      const made = sampleNode(row, at, visible)
      const lot = String(made.lot_no ?? '').trim()
      // **로트가 있을 때만 묶는다.** 로트를 안 적은 시료 둘은 서로 다를 수 있다.
      const already = lot
        ? samples.find((one) => String(one.lot_no ?? '').trim() === lot)
        : undefined
      if (already) {
        sample = already
      } else {
        sample = made
        samples.push(made)
      }
    }

    if (!has(row, 'specimen', visible)) continue
    if (sample === null) {
      // **시편은 시료에서 잘라낸 조각이다.** 시료를 안 적었으면 하나 만든다 —
      // 안 만들면 붙일 데가 없어 시편이 조용히 사라진다.
      sample = sampleNode(blankRow(), at, visible)
      samples.push(sample)
    }
    ;(sample.specimens as SpecimenNode[]).push(specimenNode(row, at, visible))
  }

  return { materials }
}

export function tally(tree: BulkRequest, rows: Row[], visible: Column[] = COLUMNS): Tally {
  let samples = 0
  let specimens = 0
  let implied = 0
  for (const material of tree.materials) {
    for (const sample of material.samples ?? []) {
      samples += 1
      specimens += (sample.specimens ?? []).length
      if (!has(rows[sample.row] ?? {}, 'sample', visible)) implied += 1
    }
  }
  return { materials: tree.materials.length, samples, specimens, implied }
}
