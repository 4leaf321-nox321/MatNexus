/**
 * 줄 폼 ↔ 정의 — **여기가 조용히 틀리는 자리다.**
 *
 * 화면은 폼이고 서버가 받는 것은 JSON 이라, 그 사이를 옮기는 코드가 하나 있다.
 * 이 코드가 칸 하나를 빠뜨리거나 빈 값을 그대로 보내면 **덱이 달라지는데 화면은
 * 멀쩡해 보인다** — 미리보기가 그것을 잡아 주지만, 미리보기도 이 변환을 거친
 * 정의를 보므로 같이 틀린다.
 *
 * 특히 무는 것:
 *
 *   1. **빈 칸을 안 보낸다.** `when: ""` 은 「늘 그린다」 가 아니라 값 하나를 찾는
 *      조건이 되어 그 줄이 통째로 사라진다.
 *   2. **상수와 값을 안 섞는다.** Prony 의 체적항은 상수 `"0.0"` 이고, 값으로
 *      바뀌면 표에 없는 열을 찾다가 덱이 안 나온다.
 *   3. **왕복해도 같다.** 고치러 들어와 저장만 눌러도 정의가 바뀌면 안 된다.
 */

import { describe, expect, it } from 'vitest'

import {
  blank,
  fromDefinitionLine,
  fromScan,
  toDefinitionLine,
} from '@/modules/fitting/deckLines'
import type { DeckLine } from '@/modules/fitting/deckLines'

describe('폼 → 정의', () => {
  it('빈 칸은 안 보낸다', () => {
    // `when: ""` 을 그대로 보내면 서버는 값 하나를 찾는 조건으로 읽는다 —
    // 그 값이 없으면 **그 줄이 통째로 빠진다.**
    const line: DeckLine = { kind: 'text', text: '*MATERIAL', when: '', note: '' }
    expect(toDefinitionLine(line)).toEqual({ text: '*MATERIAL' })
  })

  it('조건과 안내는 적었으면 보낸다', () => {
    const line: DeckLine = {
      kind: 'text',
      text: '** DENSITY 없음',
      when: 'missing:elastic.density',
      note: '밀도가 없어 뺐습니다.',
    }
    expect(toDefinitionLine(line)).toEqual({
      text: '** DENSITY 없음',
      when: 'missing:elastic.density',
      note: '밀도가 없어 뺐습니다.',
    })
  })

  it('상수 칸은 값으로 안 바뀐다', () => {
    // Prony 의 체적항. **값으로 바뀌면 표에 없는 열을 찾다가 덱이 안 나온다.**
    const line: DeckLine = {
      kind: 'rows',
      rows: 'viscoelastic',
      fields: [{ value: 'relative_modulus', format: 'free' }, { const: '0.0' }],
    }
    expect(toDefinitionLine(line)).toEqual({
      rows: 'viscoelastic',
      fields: [{ value: 'relative_modulus', format: 'free' }, { const: '0.0' }],
    })
  })

  it('x·y 를 안 주면 안 보낸다 — 그것이 곧 「정리하지 마라」 다', () => {
    // **Prony 는 점이 아니다.** x·y 를 빈 문자열로라도 보내면 서버가 점 표로 보고
    // 정렬해 버리는데, 그러면 다른 재료가 되고 덱은 멀쩡히 돈다.
    const made = toDefinitionLine({ kind: 'rows', rows: 'viscoelastic', x: '', y: '', fields: [] })
    expect('x' in made).toBe(false)
    expect('y' in made).toBe(false)
  })

  it('점 표는 x·y 를 함께 보낸다', () => {
    const made = toDefinitionLine({
      kind: 'rows',
      rows: 'table',
      x: 'plastic_strain',
      y: 'true_stress',
      fields: [{ value: 'true_stress' }],
    })
    expect(made.x).toBe('plastic_strain')
    expect(made.y).toBe('true_stress')
  })

  it('고정폭은 폭·자릿수를 달고 간다', () => {
    // **칸이 어긋나면 다른 필드로 읽힌다** — 그리고 솔버는 오류로 알려 주지 않는다.
    const made = toDefinitionLine({
      kind: 'fields',
      fields: [{ value: 'elastic.youngs_modulus', format: ['fixed', 8, 1] }],
    })
    expect(made.fields).toEqual([
      { value: 'elastic.youngs_modulus', format: ['fixed', 8, 1] },
    ])
  })
})

describe('정의 → 폼', () => {
  it('줄 종류를 알아본다', () => {
    expect(fromDefinitionLine({ block: 'elastic' }).kind).toBe('block')
    expect(fromDefinitionLine({ rows: 'table', fields: [] }).kind).toBe('rows')
    expect(fromDefinitionLine({ fields: [] }).kind).toBe('fields')
    expect(fromDefinitionLine({ text: '*MATERIAL' }).kind).toBe('text')
  })

  it('왕복해도 같다', () => {
    // **고치러 들어와 저장만 눌러도 정의가 바뀌면 안 된다.** 그러면 아무도 안
    // 건드린 솔버의 덱이 어느 날 달라져 있고, 왜인지는 아무 데도 안 남는다.
    const original = [
      { text: '*MATERIAL, NAME={name}' },
      { block: 'elastic' },
      {
        when: 'elastic.density',
        fields: [{ value: 'elastic.density', format: 'free' }],
        suffix: ',',
      },
      {
        rows: 'table',
        x: 'plastic_strain',
        y: 'true_stress',
        fields: [
          { value: 'true_stress', format: 'free' },
          { value: 'plastic_strain', format: 'free' },
        ],
      },
      {
        rows: 'viscoelastic',
        fields: [{ value: 'relative_modulus', format: 'free' }, { const: '0.0' }],
      },
    ]
    const round = original.map((one) => toDefinitionLine(fromDefinitionLine(one)))
    expect(round).toEqual(original)
  })
})

describe('새 줄', () => {
  it('종류마다 쓸 수 있는 모양으로 시작한다', () => {
    // 빈 줄에서 시작하면 사람이 무엇을 채워야 하는지 화면에 안 나온다.
    expect(blank('fields').fields).toHaveLength(1)
    expect(blank('rows').rows).toBe('table')
    expect(blank('block').block).toBe('header')
    expect(blank('text').text).toBe('')
  })
})

describe('예제 덱 초안 → 폼', () => {
  it('제안된 이름을 칸에 넣고, 없으면 비워 둔다', () => {
    // **빈칸이 곧 「여기는 네가 정해라」 다.** 짐작으로 채워 두면 사람이 그대로
    // 저장하고, 그 덱은 다른 값을 실은 채 해석에 들어간다.
    const made = fromScan({
      lines: [
        {
          kind: 'fields',
          cells: [{ suggested: 'elastic.density' }, { suggested: null }],
          join: ', ',
        },
      ],
    })
    expect(made[0].fields).toEqual([
      { value: 'elastic.density', format: 'free' },
      { value: '', format: 'free' },
    ])
  })

  it('읽어 낸 칸 폭을 그대로 옮긴다', () => {
    // **사람이 세면 틀리고, 틀려도 덱은 나온다.** 그 다음이 조용히 틀린 해석이다.
    const made = fromScan({
      lines: [{ kind: 'fields', cells: [{ suggested: null }], width: 8, precision: 1 }],
    })
    expect(made[0].fields?.[0].format).toEqual(['fixed', 8, 1])
  })

  it('표 이름은 비워 둔다 — 사람이 정한다', () => {
    // 소성인지 Prony 인지는 덱만 봐서 알 수 없고, 그것이 곧 「어느 표를 그릴까」 다.
    const made = fromScan({ lines: [{ kind: 'rows', cells: [{ suggested: null }] }] })
    expect(made[0].kind).toBe('rows')
    expect(made[0].rows).toBe('')
  })

  it('키워드 줄은 글자 그대로 온다', () => {
    const made = fromScan({ lines: [{ kind: 'text', text: '*MATERIAL, NAME=DP600' }] })
    expect(made[0]).toEqual({ kind: 'text', text: '*MATERIAL, NAME=DP600' })
  })
})

describe('값 앞에 붙는 글자', () => {
  it('저장할 때 함께 간다', () => {
    // **이것이 없으면 ANSYS·Nastran 은 아예 정의로 못 붙인다** — 명령·카드
    // 이름이 값과 같은 줄에 온다.
    const made = toDefinitionLine({
      kind: 'fields',
      prefix: 'MP,EX,',
      fields: [{ value: 'elastic.youngs_modulus' }],
      join: ',',
    })
    expect(made.prefix).toBe('MP,EX,')
  })

  it('비어 있으면 안 보낸다', () => {
    const made = toDefinitionLine({ kind: 'fields', prefix: '', fields: [] })
    expect('prefix' in made).toBe(false)
  })

  it('초안에서 그대로 온다', () => {
    const made = fromScan({
      lines: [{ kind: 'fields', cells: [{ suggested: null }], prefix: 'MAT1    ' }],
    })
    expect(made[0].prefix).toBe('MAT1    ')
  })

  it('왕복해도 같다', () => {
    const one = { prefix: 'MP,DENS,', fields: [{ value: 'elastic.density' }], join: ',' }
    expect(toDefinitionLine(fromDefinitionLine(one))).toEqual(one)
  })
})

describe('맞춤', () => {
  it('왼쪽 맞춤 덱은 왼쪽 맞춤 형식으로 온다', () => {
    // **Nastran·OptiStruct 벌크가 왼쪽 맞춤이다.** 폭만 맞고 값이 반대쪽에 붙으면
    // 이웃 필드와 붙어 솔버가 둘을 한 값으로 읽는다.
    const made = fromScan({
      lines: [{ kind: 'fields', cells: [{ suggested: null }], width: 8, precision: 1, align: 'left' }],
    })
    expect(made[0].fields?.[0].format).toEqual(['fixed_left', 8, 1])
  })

  it('오른쪽 맞춤이 기본이다', () => {
    const made = fromScan({
      lines: [{ kind: 'fields', cells: [{ suggested: null }], width: 10, precision: 9 }],
    })
    expect(made[0].fields?.[0].format).toEqual(['fixed', 10, 9])
  })
})

describe('비운 칸', () => {
  it('초안에서 빈 상수로 온다', () => {
    // **Nastran 자유 필드의 `,,` 자리다.** 값 칸으로 바꾸면 사람이 거기에 값을
    // 넣게 되고, 「기본값을 쓰라」 가 아니라 지어낸 값이 덱에 실린다.
    const made = fromScan({
      lines: [
        {
          kind: 'fields',
          cells: [{ suggested: 'elastic.youngs_modulus' }, { empty: true }, { suggested: null }],
        },
      ],
    })
    expect(made[0].fields?.[1]).toEqual({ const: '' })
  })

  it('저장할 때도 자리를 지킨다', () => {
    // **안 보내면 그 자리가 사라져 뒤 값이 한 칸씩 당겨진다.**
    const made = toDefinitionLine({
      kind: 'fields',
      fields: [{ value: 'elastic.youngs_modulus' }, { const: '' }, { value: 'elastic.density' }],
    })
    expect(made.fields).toEqual([
      { value: 'elastic.youngs_modulus' },
      { const: '' },
      { value: 'elastic.density' },
    ])
  })
})
