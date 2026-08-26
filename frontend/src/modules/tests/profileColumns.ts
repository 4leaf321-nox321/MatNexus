/**
 * 열 규칙의 **왕복** — 저장된 것을 읽고, 고친 것을 다시 쓴다.
 *
 * ## 왜 화면에서 꺼냈나
 *
 * 화면 컴포넌트 안에 있으면 시험이 1600줄짜리 페이지를 통째로 렌더해야 하고,
 * 그러면 사보타주가 안 물린다. 실제로 편집 화면에는 시험이 하나도 없었고,
 * 그래서 아래 두 결함이 배포된 채로 있었다.
 *
 * ## 결함 하나 — 단위를 적을 자리가 없었다
 *
 * JSON 파일에는 **단위 줄이 없다**(`json_tables.py` 가 `units=()` 로 고정한다).
 * 그러면 `profile.py` 가 프로파일의 `unit` 을 보는데, 화면이 만드는 정의에는
 * 그 자리가 없었다. 결과: **화면으로 만든 프로파일로는 JSON 을 영영 못 읽는다.**
 * 오류 문구는 "프로파일에서 그 열의 단위를 지정하세요" 라고 말하는데, 화면에
 * 지정할 곳이 없었다 — 막다른 길을 가리키는 안내였다.
 *
 * ## 결함 둘 — 열고 저장만 해도 규칙이 사라졌다
 *
 * 불러오기가 `rule.channel` 하나만 읽었다. 그래서 기본 프로파일
 * (`legacy_mtet`)을 편집 화면에서 열고 **아무것도 안 고치고 저장만 눌러도**
 *
 *   `{"channel":"displacement","unit":"mm"}` → `{"channel":"displacement"}`
 *   `{"skip": true}`                        → 규칙이 통째로 사라짐
 *
 * 앞엣것은 그 순간부터 모든 `.mtet` 등록을 실패시키고, 뒤엣것은 행 번호 열을
 * 뜻 없는 채널로 곡선에 끼워 넣는다(실측 파일 282개 전부에 그 열이 있다).
 *
 * ## 단위를 미리 안 채우는 이유
 *
 * 파일이 준 단위를 프로파일에 **굳히지 않는다.** 프로파일의 `unit` 은 파일을
 * 이기므로(`profile.py` 의 `mapping.get("unit") or table.units[index]`), 한 파일의
 * 단위를 굳히면 그 열을 `kPa` 로 적어 오는 다음 파일이 조용히 `MPa` 로 읽힌다.
 * 프로파일은 한 파일이 아니라 **그 장비의 모든 파일**에 걸린다.
 *
 * 실측이 그 위험을 확인해 준다 — 같은 열이 파일에 따라 단위를 달고도(55회)
 * 안 달고도(33회) 온다.
 */

import type { ProfileDefinition } from '@/modules/tests/api'

/** 열 하나를 어떻게 읽을지. **셋이 한 벌이다** — 하나만 왕복시키면 나머지가 사라진다. */
export interface ColumnRule {
  /** 우리 채널 키. 비면 '안 정함' — 버려지지는 않고 열 이름이 그대로 키가 된다. */
  channel: string
  /** 프로파일이 선언하는 단위. 비면 파일이 준 것을 쓴다. */
  unit: string
  /** 아예 안 읽을 열. 옛 앱 파일의 행 번호(`#`) 가 이것이다. */
  skip: boolean
}

export const EMPTY_RULE: ColumnRule = { channel: '', unit: '', skip: false }

export function readColumnRules(
  columns: ProfileDefinition['columns'] | undefined
): Record<string, ColumnRule> {
  const out: Record<string, ColumnRule> = {}
  for (const [name, rule] of Object.entries(columns ?? {})) {
    out[name] = {
      channel: rule?.channel ?? '',
      unit: rule?.unit ?? '',
      skip: rule?.skip === true,
    }
  }
  return out
}

export function writeColumnRules(
  map: Record<string, ColumnRule>
): NonNullable<ProfileDefinition['columns']> {
  const out: NonNullable<ProfileDefinition['columns']> = {}
  for (const [name, rule] of Object.entries(map)) {
    if (rule.skip) {
      // **버릴 열에는 채널도 단위도 안 적는다.** 읽는 쪽이 `skip` 에서 바로
      // 넘어가므로(`profile.py`), 함께 적으면 아무도 안 보는 죽은 글자가 된다.
      out[name] = { skip: true }
      continue
    }
    const written = {
      ...(rule.channel ? { channel: rule.channel } : {}),
      ...(rule.unit ? { unit: rule.unit } : {}),
    }
    // 아무것도 안 정한 열은 아예 안 적는다 — 옛 정의와 같은 모양이라 쓸데없는
    // 리비전이 안 생긴다.
    if (Object.keys(written).length > 0) out[name] = written
  }
  return out
}

/**
 * 이 열의 단위를 **믿을 수 있나.**
 *
 * 화면이 `빈 칸` 과 `단위 줄 없음` 을 둘 다 `—` 로 그리고 있었다. 그 둘은
 * 전혀 다르다 — 빈 칸은 **무차원(`1`)으로 읽히고**, 단위 줄 없음은 등록이
 * 거부된다. 저장탄성률 칸이 비어 무차원으로 읽힌 사고가 실제로 있었다.
 */
export type UnitState =
  | 'profile' // 사람이 프로파일에 적었다 — 이것이 파일을 이긴다
  | 'file' // 파일이 준 단위를 서버가 알아봤다
  | 'blank' // 단위 칸이 비었거나 `-` → **무차원으로 읽힌다**
  | 'unknown' // 파일에 적혀 있는데 서버가 모르는 표기다
  | 'absent' // 파일에 단위 줄이 아예 없다 (JSON)
  | 'unjudged' // 이 파일에는 없는 열 — 저장본에만 있다

export function unitState(input: {
  unit: string
  raw: string | undefined
  symbol: string | null | undefined
  inFile?: boolean
}): UnitState {
  if (input.unit) return 'profile'
  if (input.inFile === false) return 'unjudged'
  if (input.raw === undefined) return 'absent'
  const raw = input.raw.trim()
  if (raw === '' || raw === '-') return 'blank'
  return input.symbol ? 'file' : 'unknown'
}

/**
 * 이대로 저장하면 **등록이 실패하는가.**
 *
 * 채널로 정한 열은 단위를 알아야 한다 — 모르는 채로 넣으면 원값이 그 채널의
 * 선언 단위인 척 저장되어 10⁶배가 틀리는데 숫자는 멀쩡해 보인다. 그래서
 * 서버가 거절하고, 화면은 그것을 **저장 전에** 말해야 한다.
 */
export function unitBlocking(state: UnitState, rule: ColumnRule): boolean {
  if (rule.skip || !rule.channel) return false
  return state === 'unknown' || state === 'absent'
}

/** 그 상태를 사람 말로. 화면이 문구를 손으로 적지 않게 한 곳에 모은다. */
export function unitNote(state: UnitState, raw: string, symbol: string | null | undefined) {
  switch (state) {
    case 'profile':
      return { text: '프로파일이 정함', tone: 'muted' as const }
    case 'file':
      return {
        text: symbol && symbol !== raw.trim() ? `${raw} → ${symbol}` : raw,
        tone: 'muted' as const,
      }
    case 'blank':
      return { text: '빈 칸 → 무차원(1)', tone: 'warn' as const }
    case 'unknown':
      return { text: `${raw} — 모르는 표기`, tone: 'warn' as const }
    case 'absent':
      return { text: '파일에 단위가 없음', tone: 'warn' as const }
    case 'unjudged':
      return { text: '이 파일에 없는 열', tone: 'muted' as const }
  }
}
