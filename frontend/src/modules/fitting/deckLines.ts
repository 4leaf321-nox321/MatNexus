/**
 * 덱 정의의 **줄 문법** — 화면이 폼으로 그리기 위한 모양.
 *
 * 서버의 `matcore/export/template` 이 정본이고, 여기는 그것을 사람이 고를 수 있는
 * 목록으로 옮긴 것이다. **두 벌이라는 사실을 감추지 않는다** — 서버가 문법을
 * 넓히면 여기도 늘려야 하고, 안 늘리면 새 문법을 화면에서 못 적는다. 그때 막히는
 * 것은 미리보기가 아니라 편집기다(정의 자체는 서버가 받는다).
 */

/** 줄 한 종류. `kind` 는 화면 안에서만 쓰는 딱지 — 저장할 때는 벗긴다. */
export type LineKind = 'text' | 'block' | 'fields' | 'rows'

export type FieldSpec = {
  /** `블록.값` 또는 표의 열 이름. `const` 가 있으면 안 쓴다. */
  value?: string
  /** 값 대신 늘 이 글자. Prony 의 체적항처럼 **안 잰 자리**가 그렇다. */
  const?: string
  format?: string | [string, number, number]
}

export type DeckLine = {
  kind: LineKind
  text?: string
  /**
   * 값 앞에 붙는 글자. ANSYS 의 `MP,EX,` · Nastran 의 `MAT1    ` 처럼.
   *
   * **이것이 없으면 그 솔버는 아예 정의로 못 붙인다** — 명령·카드 이름이 값과
   * 같은 줄에 오는 솔버가 여럿이다.
   */
  prefix?: string
  block?: string
  rows?: string
  x?: string
  y?: string
  fields?: FieldSpec[]
  join?: string
  suffix?: string
  when?: string
  note?: string
}

/** 사람이 읽는 이름과 「무엇에 쓰나」. **드롭다운에 설명이 없으면 못 고른다.** */
export const LINE_KINDS: { key: LineKind; label: string; hint: string }[] = [
  { key: 'text', label: '글자', hint: '키워드 줄. {name}·{units} 를 쓸 수 있습니다.' },
  {
    key: 'fields',
    label: '값',
    hint: '카드의 값 여럿을 한 줄에. 없는 값을 꽂으려 하면 덱이 안 나옵니다.',
  },
  {
    key: 'rows',
    label: '표',
    hint: '표를 줄마다 반복. x·y 를 주면 점 표로 보고 정리합니다.',
  },
  {
    key: 'block',
    label: '묶음',
    hint: '코드가 만드는 줄 묶음. 검증·분기가 있어 정의로 못 적는 것들입니다.',
  },
]

/** 코드가 만드는 묶음. **서버의 `BLOCKS` 와 같아야 한다.** */
export const BLOCKS = [
  { key: 'header', label: '머리글 (재료 이름·근거 줄)' },
  { key: 'elastic', label: '탄성 (온도별 표까지)' },
  { key: 'thermal', label: '열물성' },
]

export const FORMATS = [
  { key: 'free', label: '자유 형식 (Abaqus·JSON)' },
  { key: 'fixed', label: '고정폭 · 오른쪽 맞춤 (LS-DYNA 10 · Radioss 20)' },
  // **왼쪽 맞춤이 따로 필요하다.** Nastran·OptiStruct 벌크가 그쪽이고, 폭만 맞고
  // 값이 반대쪽에 붙으면 이웃 필드와 붙어 솔버가 둘을 한 값으로 읽는다.
  { key: 'fixed_left', label: '고정폭 · 왼쪽 맞춤 (Nastran·OptiStruct 8)' },
]

/** 새 줄 하나. */
export function blank(kind: LineKind): DeckLine {
  if (kind === 'fields') return { kind, fields: [{ value: '', format: 'free' }] }
  if (kind === 'rows') return { kind, rows: 'table', fields: [{ value: '', format: 'free' }] }
  if (kind === 'block') return { kind, block: 'header' }
  return { kind, text: '' }
}

/**
 * 화면의 줄 → 저장할 줄. **빈 칸을 안 보낸다.**
 *
 * 빈 문자열을 그대로 보내면 서버는 「적었는데 비었다」 로 읽는다 — `suffix: ""` 와
 * `suffix` 없음은 결과가 같지만, `when: ""` 은 「늘 그린다」 가 아니라 값 하나를
 * 찾는 조건이 되어 덱이 통째로 달라진다.
 */
export function toDefinitionLine(line: DeckLine): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const put = (key: string, value: unknown) => {
    if (value !== undefined && value !== null && value !== '') out[key] = value
  }
  if (line.kind === 'text') put('text', line.text)
  if (line.kind === 'block') put('block', line.block)
  if (line.kind === 'rows') {
    put('rows', line.rows)
    put('x', line.x)
    put('y', line.y)
  }
  if (line.kind === 'fields' || line.kind === 'rows') {
    out.fields = (line.fields ?? []).map((field) => {
      const one: Record<string, unknown> = {}
      // **빈 상수도 보낸다.** `''` 는 「비운 칸」 이고 자리를 차지한다 —
      // 안 보내면 그 자리가 사라져 뒤 값이 한 칸씩 당겨진다.
      if (field.const !== undefined) one.const = field.const
      else one.value = field.value ?? ''
      if (field.format) one.format = field.format
      return one
    })
    put('prefix', line.prefix)
    put('join', line.join)
    put('suffix', line.suffix)
    if (line.kind === 'fields') put('text', line.text)
  }
  put('when', line.when)
  put('note', line.note)
  return out
}

/** 저장된 줄 → 화면의 줄. 고치러 들어올 때 쓴다. */
export function fromDefinitionLine(raw: Record<string, unknown>): DeckLine {
  const kind: LineKind =
    'block' in raw ? 'block' : 'rows' in raw ? 'rows' : 'fields' in raw ? 'fields' : 'text'
  return {
    kind,
    text: typeof raw.text === 'string' ? raw.text : undefined,
    prefix: typeof raw.prefix === 'string' ? raw.prefix : undefined,
    block: typeof raw.block === 'string' ? raw.block : undefined,
    rows: typeof raw.rows === 'string' ? raw.rows : undefined,
    x: typeof raw.x === 'string' ? raw.x : undefined,
    y: typeof raw.y === 'string' ? raw.y : undefined,
    fields: Array.isArray(raw.fields) ? (raw.fields as FieldSpec[]) : undefined,
    join: typeof raw.join === 'string' ? raw.join : undefined,
    suffix: typeof raw.suffix === 'string' ? raw.suffix : undefined,
    when: typeof raw.when === 'string' ? raw.when : undefined,
    note: typeof raw.note === 'string' ? raw.note : undefined,
  }
}

/**
 * 읽어 낸 초안 → 화면의 줄.
 *
 * **제안된 이름을 칸에 그대로 넣는다.** 제안이 없는 칸은 비워 둔다 — 그 빈칸이
 * 곧 「여기는 네가 정해라」 이고, 짐작으로 채워 두면 사람이 그대로 저장한다.
 *
 * 칸 폭도 함께 옮긴다. **사람이 남의 덱을 보고 폭을 세는 것은 틀리기 쉽고,
 * 틀려도 덱은 멀쩡히 나온다** — 그 다음이 조용히 틀린 해석이다.
 */
export function fromScan(scanned: {
  lines: {
    kind: string
    text?: string | null
    cells?: { suggested?: string | null; empty?: boolean }[]
    prefix?: string
    join?: string
    suffix?: string
    width?: number | null
    align?: string
    precision?: number | null
  }[]
}): DeckLine[] {
  return scanned.lines.map((one) => {
    if (one.kind === 'text') return { kind: 'text', text: one.text ?? '' }
    const format: string | [string, number, number] =
      one.width != null
        ? [one.align === 'left' ? 'fixed_left' : 'fixed', one.width, one.precision ?? 9]
        : 'free'
    const fields = (one.cells ?? []).map((cell) =>
      // **비운 칸은 비운 채로 지킨다.** Nastran 자유 필드의 `,,` 자리를 값 칸으로
      // 바꾸면 사람이 거기에 값을 넣게 되고, 그러면 「기본값을 쓰라」 가 아니라
      // 지어낸 값이 덱에 실린다.
      cell.empty ? { const: '' } : { value: cell.suggested ?? '', format }
    )
    const common = { fields, prefix: one.prefix, join: one.join, suffix: one.suffix }
    if (one.kind === 'rows') {
      // **표 이름은 사람이 정한다.** 소성인지 Prony 인지는 덱만 봐서 알 수 없고,
      // 그것이 곧 「어느 표를 여기 그릴까」 다.
      return { kind: 'rows', rows: '', ...common }
    }
    return { kind: 'fields', ...common }
  })
}
