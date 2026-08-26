/**
 * 시험 종류의 **채널·조건을 여러 개 한 번에** 받는다.
 *
 * ## 왜 필요했나
 *
 * 하나씩 「추가」 를 눌러 키·이름·차원·필수를 채우는 화면이었다. DMA 스윕은
 * 채널이 아홉이고 인장은 조건이 여섯이다 — 그걸 한 줄씩 만드는 동안 사람은
 * **같은 판단을 아홉 번** 한다. 그리고 그 목록은 대개 이미 어딘가에 적혀 있다
 * (장비 설명서·엑셀·기존 정의).
 *
 * 재료 여러 개 등록이 같은 문제를 이미 겪었고, 표로 붙여넣는 장치가 그때
 * `shared/components/PasteGrid` 로 나왔다. 여기서 다시 만들지 않는다.
 *
 * ## 화면 밖에 있는 이유
 *
 * 해석은 **틀릴 수 있는 부분**이다 — 차원 이름을 한글로 적었을 때, 필수 칸에
 * `Y` 라고 적었을 때, 키에 공백이 있을 때. 그것을 화면 안에 두면 시험이
 * 편집기를 통째로 렌더해야 하고, 그러면 사보타주가 잘 안 물린다.
 *
 * ## 지어내지 않는다
 *
 * 모르는 차원·모르는 종류는 **기본값으로 때우지 않고 그 줄을 문제로 돌려준다.**
 * `길이` 라고 적으려다 `길이(mm)` 라고 적은 줄을 조용히 `length` 로 만들면,
 * 사람은 자기가 적은 대로 들어간 줄 안다.
 */

import { toChannelKey } from '@/modules/tests/keys'
import { DIMENSIONS, DIMENSION_LABELS, SI_BY_DIMENSION, VALUE_TYPES } from '@/shared/units'

/** 붙여넣기 표의 열. `header` 가 사람이 보는 이름이자 복사해 갈 때의 글자다. */
export const CHANNEL_COLUMNS = [
  { key: 'key', header: '키', help: '영문·숫자·밑줄. `Storage modulus` 처럼 적어도 다듬습니다.' },
  { key: 'label', header: '이름', help: '화면에 뜨는 이름.' },
  { key: 'dimension', header: '차원', help: '`length` 또는 `길이`. 저장 단위는 여기서 정해집니다.' },
  { key: 'required', header: '필수', help: '`Y` 면 그 열이 없는 파일은 등록이 실패합니다.' },
] as const

export const CONDITION_COLUMNS = [
  { key: 'key', header: '키', help: '영문·숫자·밑줄.' },
  { key: 'label', header: '이름', help: '화면에 뜨는 이름.' },
  { key: 'value_type', header: '종류', help: '`number` 또는 `숫자`. 비우면 숫자.' },
  { key: 'dimension', header: '차원', help: '숫자일 때만. `temperature` 또는 `온도`.' },
  { key: 'required', header: '필수', help: '`Y` 면 안 적고는 못 올립니다.' },
] as const

export interface ParsedRow {
  key: string
  label: string
  value_type: string
  dimension: string | null
  si_unit: string | null
  is_required: boolean
}

export interface Problem {
  /** 표에서 몇 번째 줄인가. 사람이 세는 번호(1부터). */
  line: number
  said: string
}

/** 차원 이름 → 키. **한글로 적어도 받는다** — 화면이 한글로 보여 주기 때문이다. */
const DIMENSION_BY_NAME: Record<string, string> = {
  ...Object.fromEntries(DIMENSIONS.map((one) => [one.toLowerCase(), one])),
  ...Object.fromEntries(
    Object.entries(DIMENSION_LABELS).map(([key, label]) => [label.toLowerCase(), key])
  ),
  // `무차원 (비율·개수)` 는 라벨이 길다. 짧게 적는 사람이 있다.
  무차원: 'dimensionless',
}

const TYPE_BY_NAME: Record<string, string> = {
  ...Object.fromEntries(VALUE_TYPES.map((one) => [one.value, one.value])),
  ...Object.fromEntries(VALUE_TYPES.map((one) => [one.label, one.value])),
}

/** `Y`·`예`·`필수`·`true`·`1` 이면 참. 비면 거짓 — **비운 것을 참으로 읽지 않는다.** */
function truthy(text: string): boolean {
  return ['y', 'yes', '예', '필수', 'true', '1', 'o', 'ㅇ'].includes(text.trim().toLowerCase())
}

/**
 * 붙여넣은 표를 줄로 바꾼다. **한 줄이라도 문제면 그 줄만 문제로 돌려준다** —
 * 나머지는 살린다. 전부 막으면 오타 하나에 아홉 줄을 다시 붙여야 한다.
 */
export function parseRows(
  kind: 'channel' | 'condition',
  rows: string[][],
  taken: string[] = []
): { rows: ParsedRow[]; problems: Problem[] } {
  const parsed: ParsedRow[] = []
  const problems: Problem[] = []
  const used = new Set(taken)

  rows.forEach((cells, index) => {
    const line = index + 1
    const at = (column: number) => (cells[column] ?? '').trim()
    if (!cells.some((cell) => cell.trim())) return // 빈 줄. 표에는 늘 하나 남아 있다.

    const key = toChannelKey(at(0))
    const label = at(1) || at(0)
    if (!key) {
      problems.push({ line, said: '키가 비었습니다.' })
      return
    }
    if (used.has(key)) {
      // **조용히 덮지 않는다.** 같은 키가 둘이면 나중 것이 앞을 지운다.
      problems.push({ line, said: `키 '${key}' 가 이미 있습니다.` })
      return
    }

    const typeText = kind === 'condition' ? at(2) : ''
    const dimensionText = kind === 'condition' ? at(3) : at(2)
    const requiredText = kind === 'condition' ? at(4) : at(3)

    let value_type = 'number'
    if (kind === 'condition' && typeText) {
      const found = TYPE_BY_NAME[typeText.toLowerCase()] ?? TYPE_BY_NAME[typeText]
      if (!found) {
        problems.push({
          line,
          said: `모르는 종류입니다: '${typeText}'. 쓸 수 있는 것: ${VALUE_TYPES.map(
            (one) => one.label
          ).join('·')}`,
        })
        return
      }
      value_type = found
    }

    // 숫자가 아닌 조건에는 차원이 없다. 억지로 붙이면 단위 칸이 생긴다.
    const wantsDimension = kind === 'channel' || value_type === 'number'
    let dimension: string | null = null
    if (wantsDimension) {
      if (!dimensionText) {
        problems.push({ line, said: '차원이 비었습니다. 저장 단위가 여기서 정해집니다.' })
        return
      }
      const found = DIMENSION_BY_NAME[dimensionText.toLowerCase()]
      if (!found) {
        problems.push({ line, said: `모르는 차원입니다: '${dimensionText}'.` })
        return
      }
      dimension = found
    }

    used.add(key)
    parsed.push({
      key,
      label,
      value_type,
      dimension,
      // **저장 단위는 고르는 것이 아니다.** 차원이 정하고, 화면도 그렇게 한다.
      si_unit: dimension ? (SI_BY_DIMENSION[dimension] ?? '1') : null,
      is_required: truthy(requiredText),
    })
  })

  return { rows: parsed, problems }
}
