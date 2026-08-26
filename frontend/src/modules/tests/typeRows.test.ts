/**
 * 채널·조건 여러 개 붙여넣기 — **해석이 조용히 틀리지 않는가.**
 *
 * 여기서 지어내면 사람은 자기가 적은 대로 들어간 줄 안다. 그리고 시험 종류
 * 정의는 **나중에 못 바꾸는 자리가 있다**(데이터가 붙으면 키·단위·차원이
 * 잠긴다) — 잘못 들어간 줄을 되돌리는 비용이 크다.
 */

import { describe, expect, it } from 'vitest'

import { parseRows } from '@/modules/tests/typeRows'

describe('채널', () => {
  it('키를 다듬고 차원에서 저장 단위를 정한다', () => {
    const { rows, problems } = parseRows('channel', [
      ['Storage modulus', '저장탄성률', 'stress', 'Y'],
      ['displacement', '변위', '길이', ''],
    ])
    expect(problems).toEqual([])
    expect(rows[0]).toMatchObject({
      key: 'storage_modulus',
      label: '저장탄성률',
      dimension: 'stress',
      si_unit: 'Pa',
      is_required: true,
    })
    // **한글 차원도 받는다** — 화면이 한글로 보여 주므로 그대로 적는 사람이 있다.
    expect(rows[1]).toMatchObject({ dimension: 'length', si_unit: 'm', is_required: false })
  })

  it('이름이 비면 키로 적은 글자를 쓴다', () => {
    const { rows } = parseRows('channel', [['Angular frequency', '', 'angular_frequency', '']])
    expect(rows[0].label).toBe('Angular frequency')
  })

  it('필수를 비우면 거짓이다', () => {
    // **비운 것을 참으로 읽지 않는다.** 필수로 두면 그 열이 없는 파일이 전부
    // 등록에 실패한다 — 같은 장비라도 측정 항목이 매번 같지는 않다.
    const { rows } = parseRows('channel', [['force', '하중', 'force', '']])
    expect(rows[0].is_required).toBe(false)
  })

  it('여러 표기의 참을 받는다', () => {
    const said = ['Y', 'yes', '예', '필수', 'true', '1', 'O']
    const { rows } = parseRows(
      'channel',
      said.map((one, index) => [`ch${index}`, '', 'force', one])
    )
    expect(rows.every((row) => row.is_required)).toBe(true)
  })
})

describe('조건', () => {
  it('종류를 한글로도 받는다', () => {
    const { rows, problems } = parseRows('condition', [
      ['temperature', '시험 온도', '숫자', '온도', 'Y'],
      ['sensor_type', '센서 종류', '문자', '', ''],
    ])
    expect(problems).toEqual([])
    expect(rows[0]).toMatchObject({ value_type: 'number', dimension: 'temperature', si_unit: 'K' })
    // **숫자가 아니면 차원이 없다.** 억지로 붙이면 단위 칸이 생긴다.
    expect(rows[1]).toMatchObject({ value_type: 'text', dimension: null, si_unit: null })
  })

  it('종류를 비우면 숫자다', () => {
    const { rows } = parseRows('condition', [['preload', '예하중', '', 'force', '']])
    expect(rows[0].value_type).toBe('number')
  })
})

describe('모르면 지어내지 않는다', () => {
  it('모르는 차원은 그 줄만 문제로 돌려준다', () => {
    const { rows, problems } = parseRows('channel', [
      ['a', '가', '길이', ''],
      ['b', '나', '길이(mm)', ''],
      ['c', '다', 'force', ''],
    ])
    // **나머지는 살린다.** 전부 막으면 오타 하나에 아홉 줄을 다시 붙여야 한다.
    expect(rows.map((row) => row.key)).toEqual(['a', 'c'])
    expect(problems).toHaveLength(1)
    expect(problems[0]).toMatchObject({ line: 2 })
    expect(problems[0].said).toContain('길이(mm)')
  })

  it('모르는 종류도 마찬가지다', () => {
    const { problems } = parseRows('condition', [['a', '가', '숫자열', '온도', '']])
    expect(problems[0].said).toContain('숫자열')
    // 무엇을 쓸 수 있는지까지 말해야 고칠 수 있다.
    expect(problems[0].said).toContain('숫자')
  })

  it('차원이 비면 막는다', () => {
    const { problems } = parseRows('channel', [['a', '가', '', '']])
    expect(problems[0].said).toContain('차원')
  })

  it('키가 비면 막는다', () => {
    const { problems } = parseRows('channel', [['', '이름만', 'force', '']])
    expect(problems[0].said).toContain('키')
  })
})

describe('겹치는 키', () => {
  it('표 안에서 겹치면 막는다', () => {
    // **조용히 덮지 않는다.** 나중 것이 앞을 지우면 아홉 줄을 붙였는데 여덟만
    // 들어가고, 그 사실은 저장하고 나서야 보인다.
    const { rows, problems } = parseRows('channel', [
      ['force', '하중', 'force', ''],
      ['Force', '하중 2', 'force', ''],
    ])
    expect(rows).toHaveLength(1)
    expect(problems[0].said).toContain('force')
  })

  it('이미 있는 키와 겹쳐도 막는다', () => {
    const { rows, problems } = parseRows(
      'channel',
      [['displacement', '변위', 'length', '']],
      ['displacement']
    )
    expect(rows).toEqual([])
    expect(problems).toHaveLength(1)
  })
})

describe('빈 줄', () => {
  it('빈 줄은 문제가 아니다', () => {
    // 표에는 늘 빈 줄이 하나 남아 있다(`PasteGrid`).
    const { rows, problems } = parseRows('channel', [
      ['force', '하중', 'force', ''],
      ['', '', '', ''],
    ])
    expect(rows).toHaveLength(1)
    expect(problems).toEqual([])
  })
})
