/**
 * 덱 정의의 **줄 문법** — 화면이 폼으로 그리기 위한 모양.
 *
 * 서버의 `matcore/export/template` 이 정본이고, 여기는 그것을 사람이 고를 수 있는
 * 목록으로 옮긴 것이다. **두 벌이라는 사실을 감추지 않는다** — 서버가 문법을
 * 넓히면 여기도 늘려야 하고, 안 늘리면 새 문법을 화면에서 못 적는다. 그때 막히는
 * 것은 미리보기가 아니라 편집기다(정의 자체는 서버가 받는다).
 */

/**
 * 줄 한 종류. `kind` 는 화면 안에서만 쓰는 딱지 — 저장할 때는 벗긴다.
 *
 * `advanced` 는 폼으로 못 그리는 줄이다 — `each`(묶음마다 반복) · `pack`(칸을 N 개씩
 * 끊기) · `fail`(값 검사) · 말만 남기는 줄(ADR 0038). **원형 그대로 들고 다닌다** — 폼으로
 * 옮겼다 돌리면 칸이 빠져 기본 형식을 옮긴 정의판이 저장 한 번에 달라진다.
 */
export type LineKind = 'text' | 'plain' | 'block' | 'fields' | 'rows' | 'advanced'

/** 칸 형식 — `"free"` · `["fixed", 폭, 자릿수]` · `["spec", ">10d"]`(파이썬 형식). */
export type Format = string | [string, number, number] | [string, string]

export type FieldSpec = {
  /** `블록.값` 또는 표의 열 이름. `const` 가 있으면 안 쓴다. */
  value?: string
  /** 값 대신 늘 이 글자. Prony 의 체적항처럼 **안 잰 자리**가 그렇다. */
  const?: string
  /**
   * 값·열을 **계산해서** 적는 칸. `true_stress / 1000` · `elastic.youngs_modulus /
   * (2 * (1 + elastic.poisson_ratio))`. 사칙연산·`^`·괄호·sqrt/abs/exp/log/log10/min/max,
   * 비교·and/or/not·`A if 조건 else B`, 표 함수 first/last/sum/count….
   * 열 이름은 표 줄에서만, `블록.값` 은 어디서나.
   */
  expr?: string
  format?: Format
  /** 이 칸만의 조건. 거짓이면 `default` 를 적거나(있으면) 칸을 뺀다. */
  when?: string
  /** 조건이 거짓이거나 값이 없을 때 대신 적을 글자 — 큰칸의 빈 필드(공백 16칸). */
  default?: string
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
  /** `advanced` 줄의 원형 — 저장할 때 그대로 나간다(`when`·`note` 는 위 칸이 이긴다). */
  raw?: Record<string, unknown>
  /** 폼이 모르는 칸(묶음의 `comment` 같은 것) — **버리지 않고** 저장할 때 되돌린다. */
  extra?: Record<string, unknown>
}

/** 폼이 아는 줄 칸. 그 밖의 칸은 `extra` 로 들고 다닌다. */
const KNOWN_LINE_KEYS = new Set([
  'text',
  'plain',
  'prefix',
  'block',
  'rows',
  'x',
  'y',
  'fields',
  'join',
  'suffix',
  'when',
  'note',
])

/** 폼으로 못 그리는 줄인가 — `each`·`pack`·`fail`, 그리고 말만 남기는 줄. */
function isAdvanced(raw: Record<string, unknown>): boolean {
  if ('each' in raw || 'pack' in raw || 'fail' in raw) return true
  const draws = 'text' in raw || 'fields' in raw || 'rows' in raw || 'block' in raw
  return !draws && 'note' in raw
}

/** 사람이 읽는 이름과 「무엇에 쓰나」. **드롭다운에 설명이 없으면 못 고른다.** */
export const LINE_KINDS: { key: LineKind; label: string; hint: string }[] = [
  {
    key: 'text',
    label: '글자',
    hint: '키워드 줄. {name}·{units}·{id}(재료 번호)·{식:형식} 를 쓸 수 있습니다.',
  },
  {
    key: 'plain',
    label: '글자 줄',
    hint: '카드 값이 안 드는 줄 — 옵션 숫자·플래그·주석. 적은 그대로 나갑니다.',
  },
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
  {
    key: 'advanced',
    label: '고급',
    hint: '묶음마다 반복(each) · 칸을 N 개씩 끊기(pack) · 값 검사(fail) · 말만 남기기. JSON 으로 고칩니다.',
  },
]

/** 코드가 만드는 묶음. **서버의 `BLOCKS` 와 같아야 한다.** */
export const BLOCKS = [
  { key: 'header', label: '머리글 (재료 이름·근거 줄 — comment 로 주석 기호)' },
  { key: 'provenance', label: '근거 줄만' },
  { key: 'elastic', label: '탄성 (Abaqus, 온도별 표까지)' },
  { key: 'thermal', label: '열물성 (Abaqus)' },
  { key: 'radioss_unit', label: 'Radioss /UNIT (단위계 선언)' },
]

export const FORMATS = [
  { key: 'free', label: '자유 형식 (Abaqus·JSON)' },
  { key: 'fixed', label: '고정폭 · 오른쪽 맞춤 (LS-DYNA 10 · Radioss 20)' },
  // **왼쪽 맞춤이 따로 필요하다.** Nastran·OptiStruct 벌크가 그쪽이고, 폭만 맞고
  // 값이 반대쪽에 붙으면 이웃 필드와 붙어 솔버가 둘을 한 값으로 읽는다.
  { key: 'fixed_left', label: '고정폭 · 왼쪽 맞춤 (Nastran·OptiStruct 8)' },
  // 정수 칸(재료 번호 `>10d`)·주석의 유효숫자(`.6g`) — 파이썬 형식 문자열 그대로.
  { key: 'spec', label: '형식 문자열 (>10d · .6g · <16)' },
]

/** 새 줄 하나. */
export function blank(kind: LineKind): DeckLine {
  if (kind === 'advanced') {
    // 말만 남기는 줄로 시작한다 — 덱에는 아무것도 안 적으니 비워 둔 채 저장해도 해가 없다.
    return { kind, raw: { note: 'each · pack · fail 줄을 JSON 으로 적습니다' } }
  }
  if (kind === 'fields') return { kind, fields: [{ value: '', format: 'free' }] }
  if (kind === 'rows') return { kind, rows: 'table', fields: [{ value: '', format: 'free' }] }
  if (kind === 'block') return { kind, block: 'header' }
  return { kind, text: '' }
}

/** 이 칸이 사람에게 보이는 이름 — 편집기의 딱지와 고급 목록이 같이 쓴다. */
export function fieldLabel(field: FieldSpec, at: number): string {
  if (field.const !== undefined) return `"${field.const}"`
  if (field.expr !== undefined) return `= ${field.expr || '…'}`
  return field.value || `${at + 1}번 칸`
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
  if (line.kind === 'advanced') {
    // **원형 그대로.** 조건·말만 묶음 칸이 이긴다 — 묶음 조건이 이 줄에도 적힌다.
    const { when: _when, note: _note, ...rest } = line.raw ?? {}
    void _when
    void _note
    Object.assign(out, rest)
    put('when', line.when)
    put('note', line.note)
    return out
  }
  // 폼이 모르는 칸을 먼저 깔고, 아는 칸이 위에 선다.
  Object.assign(out, line.extra ?? {})
  // **빈 글자 줄도 보낸다** — Radioss 는 빈 줄도 한 줄로 읽는다(기본값 자리). 덱은 `{}` 와
  // 같게 나오지만, 정의가 저장 한 번에 달라지면 코드판과 견준 결과가 무너진다.
  if (line.kind === 'text') out.text = line.text ?? ''
  if (line.kind === 'plain') {
    // **빈 글자 줄도 보낸다.** 빈 줄이 곧 그 자리다 — Nastran 의 빈 계속 줄처럼.
    out.text = line.text ?? ''
    out.plain = true
  }
  if (line.kind === 'block') put('block', line.block)
  if (line.kind === 'rows') {
    put('rows', line.rows)
    put('x', line.x)
    put('y', line.y)
  }
  if (line.kind === 'fields' || line.kind === 'rows') {
    out.fields = (line.fields ?? []).map((field) => {
      // **칸의 다른 칸(when·default)은 그대로 둔다** — 큰칸의 빈 필드가 거기 산다.
      const { value: _value, const: _const, expr: _expr, format: _format, ...rest } = field
      void _value
      void _const
      void _expr
      void _format
      const one: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(rest)) {
        // 빈 `when` 은 안 보낸다(값 하나를 찾는 조건이 된다). 빈 `default` 는 **보낸다** —
        // 「비운다」 가 곧 그 뜻이다(LS-DYNA 열물성의 밀도 칸).
        if (value === undefined || (key === 'when' && value === '')) continue
        one[key] = value
      }
      // **빈 상수도 보낸다.** `''` 는 「비운 칸」 이고 자리를 차지한다 —
      // 안 보내면 그 자리가 사라져 뒤 값이 한 칸씩 당겨진다.
      if (field.const !== undefined) one.const = field.const
      else if (field.expr !== undefined) one.expr = field.expr
      else one.value = field.value ?? ''
      if (field.format) one.format = field.format
      return one
    })
    put('prefix', line.prefix)
    // **빈 구분자도 보낸다.** `""` 은 「칸을 붙여 적는다」(고정폭)이고, 안 보내면 서버가
    // 기본값 `", "` 를 끼운다 — LS-DYNA·Radioss·Nastran 카드의 칸 사이에 쉼표가 들어가
    // 다른 필드로 읽힌다. 예제 덱에서 시작한 고정폭 정의가 저장 한 번에 그렇게 됐다
    // (2026-09-28, 기본 형식의 정의판을 편집기에 통과시켜 보고 드러났다).
    if (line.join !== undefined && line.join !== null) out.join = line.join
    put('suffix', line.suffix)
    if (line.kind === 'fields') put('text', line.text)
  }
  put('when', line.when)
  put('note', line.note)
  return out
}

/** 저장된 줄 → 화면의 줄. 고치러 들어올 때 쓴다. */
export function fromDefinitionLine(raw: Record<string, unknown>): DeckLine {
  if (isAdvanced(raw)) {
    return {
      kind: 'advanced',
      raw,
      when: typeof raw.when === 'string' ? raw.when : undefined,
      note: typeof raw.note === 'string' ? raw.note : undefined,
    }
  }
  const extra: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (!KNOWN_LINE_KEYS.has(key)) extra[key] = value
  }
  const kind: LineKind =
    'block' in raw
      ? 'block'
      : 'rows' in raw
        ? 'rows'
        : 'fields' in raw
          ? 'fields'
          : raw.plain === true
            ? 'plain'
            : 'text'
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
    ...(Object.keys(extra).length ? { extra } : {}),
  }
}

/** 고급 줄을 사람이 읽는 한 줄로 — 묶음 머리에 적는다. */
export function describeAdvanced(raw: Record<string, unknown>): string {
  if ('each' in raw) {
    const count = Array.isArray(raw.lines) ? raw.lines.length : 0
    return `「${String(raw.each)}」 묶음마다 줄 ${count}개`
  }
  if ('pack' in raw) return `칸을 ${String(raw.per_line ?? '?')}개씩 끊어 적기`
  if ('fail' in raw) return `거절 — ${String(raw.fail).slice(0, 40)}`
  return `말만 남기기 — ${String(raw.note ?? '').slice(0, 40)}`
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
    const format: Format =
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
