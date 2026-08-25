/**
 * 표에 붙여 넣고, 나무로 묶고, 흠을 짚는다.
 *
 * **엑셀에서 붙여 넣으면 탭이 온다.** 그것을 안 받으면 사람은 한 줄이 통째로
 * Grade 가 된 것을 보고서야 안다 — 그때는 이미 스무 개를 잘못 만든 뒤다.
 *
 * 묶는 규칙(「빈 칸은 위와 같다」)은 여기에만 산다. 서버가 다시 해석하게 하면
 * 규칙이 두 곳에 살고, 언젠가 갈라진다.
 */

import { describe, expect, it } from 'vitest'

import {
  COLUMNS,
  blankRow,
  blankRows,
  carried,
  group,
  initialShown,
  isEmpty,
  paste,
  problems,
  spreads,
  tally,
} from '@/modules/materials/bulkRows'
import type { Column, Row } from '@/modules/materials/bulkRows'

const AT = (key: string) => COLUMNS.findIndex((column) => column.key === key)

/** 흔한 재료 한 줄. */
function row(values: Record<string, string>): Row {
  return { ...blankRow(), ...values }
}

const SECC = {
  'material.family': 'Metal',
  'material.category': 'Steel',
  'material.grade': 'SECC',
  'material.details': 'MDOI',
  'material.spec_thickness': '1.0',
}

describe('붙여 넣기', () => {
  it('탭으로 나눈다', () => {
    // 엑셀에서 그대로 붙여 넣는 것이 실제 작업이다.
    const rows = paste(blankRows(2), 'Metal\tSteel\tSECC', 0, 0, COLUMNS)
    expect(rows[0]).toMatchObject({
      'material.family': 'Metal',
      'material.category': 'Steel',
      'material.grade': 'SECC',
    })
  })

  it('탭이 없으면 쉼표로 나눈다', () => {
    const rows = paste(blankRows(2), 'Metal, Steel, SGCC\nMetal, Steel, SPCC', 0, 0, COLUMNS)
    expect(rows[0]['material.grade']).toBe('SGCC')
    expect(rows[1]['material.grade']).toBe('SPCC')
  })

  it('탭이 있으면 쉼표는 값의 일부다', () => {
    // `1,000` 이 두 칸으로 갈라지면 안 된다.
    const rows = paste(blankRows(1), 'SECC\t1,000', 0, AT('material.grade'), COLUMNS)
    expect(rows[0]['material.details']).toBe('1,000')
  })

  it('줄이 모자라면 늘린다', () => {
    // **안 늘리면 나머지가 조용히 사라진다.** 사람은 20줄을 붙여 넣고 5건만
    // 만들어진 것을 나중에 목록에서 안다.
    const rows = paste(blankRows(2), 'A\nB\nC\nD', 0, 0, COLUMNS)
    expect(rows).toHaveLength(4)
    expect(rows[3]['material.family']).toBe('D')
  })

  it('보이는 열에만 채운다', () => {
    // **안 보이는 칸으로 값이 새면 사람은 그것을 영영 못 본다.** 두 칸만 켜
    // 두고 셋을 붙여 넣으면 셋째는 버려야 한다.
    const visible: Column[] = COLUMNS.filter((column) =>
      ['material.grade', 'material.details'].includes(column.key)
    )
    const rows = paste(blankRows(1), 'SECC\tMDOI\t1.0', 0, 0, visible)
    expect(rows[0]['material.grade']).toBe('SECC')
    expect(rows[0]['material.details']).toBe('MDOI')
    expect(rows[0]['material.spec_thickness']).toBe('')
  })

  it('빈 줄은 넘긴다', () => {
    // 붙여 넣기 끝에 빈 줄이 남는 것이 보통이다.
    const rows = paste(blankRows(1), 'A\n\n  \nB', 0, 0, COLUMNS)
    expect(rows.filter((one) => !isEmpty(one))).toHaveLength(2)
  })

  it('한 칸짜리는 글자 그대로 둔다', () => {
    // 별칭에 `도어 이너, 아우터` 를 붙여 넣었는데 두 칸으로 갈라지면 안 된다.
    expect(spreads('도어 이너, 아우터')).toBe(false)
    expect(spreads('SECC\tMDOI')).toBe(true)
    expect(spreads('SECC\nSGCC')).toBe(true)
  })
})

describe('열 켜고 끄기', () => {
  it('열자마자 보이는 것은 재료뿐이다', () => {
    // 스물 몇 개를 다 펼치면 아무것도 못 읽는다.
    const shown = initialShown()
    expect([...shown].every((key) => key.startsWith('material.'))).toBe(true)
    expect(shown.size).toBeGreaterThan(3)
  })

  it('시료·시편 칸도 켤 수 있게 있다', () => {
    // 이 표가 셋을 한꺼번에 받는다는 것 자체를 잡아 둔다.
    const groups = new Set(COLUMNS.map((column) => column.group))
    expect(groups).toEqual(new Set(['material', 'sample', 'specimen']))
  })
})

describe('나무로 묶기', () => {
  it('재료 칸이 빈 줄은 위 재료에 붙는다', () => {
    const tree = group([
      row({ ...SECC, 'sample.lot_no': 'LOT-A' }),
      row({ 'sample.lot_no': 'LOT-B' }),
    ])
    expect(tree.materials).toHaveLength(1)
    expect(tree.materials[0].samples).toHaveLength(2)
    // 줄 번호를 달고 간다 — 실패했을 때 표의 그 줄을 짚어야 한다.
    expect((tree.materials[0].samples as { row: number }[])[1].row).toBe(1)
  })

  it('시료 칸이 빈 줄은 위 시료에 붙는다', () => {
    const tree = group([
      row({ ...SECC, 'sample.lot_no': 'LOT-A', 'specimen.orientation': 'MD' }),
      row({ 'specimen.orientation': 'MD' }),
      row({ 'specimen.orientation': 'TD' }),
    ])
    const samples = tree.materials[0].samples as { specimens: unknown[] }[]
    expect(samples).toHaveLength(1)
    expect(samples[0].specimens).toHaveLength(3)
  })

  it('새 시료 줄은 새 시료를 연다', () => {
    const tree = group([
      row({ ...SECC, 'sample.lot_no': 'LOT-A', 'specimen.orientation': 'MD' }),
      row({ 'sample.lot_no': 'LOT-B', 'specimen.orientation': 'MD' }),
    ])
    const samples = tree.materials[0].samples as { specimens: unknown[] }[]
    expect(samples).toHaveLength(2)
    expect(samples.map((one) => one.specimens.length)).toEqual([1, 1])
  })

  it('시료를 안 적고 시편만 적으면 시료가 하나 생긴다', () => {
    // **시편은 시료에서 잘라낸 조각이다.** 안 만들면 붙일 데가 없어 시편이
    // 조용히 사라진다 — 사람은 표를 보며 「분명 넣었는데」 를 한다.
    const rows = [row({ ...SECC, 'specimen.orientation': 'MD' })]
    const tree = group(rows)
    expect(tree.materials[0].samples).toHaveLength(1)
    expect(tally(tree, rows).implied).toBe(1)
  })

  it('빈 줄은 아무것도 만들지 않는다', () => {
    expect(group(blankRows(5)).materials).toEqual([])
  })

  it('값이 없는 칸은 보내지 않는다', () => {
    // 빈 문자열을 보내면 `''` 가 저장되고, 나중에 「비었나」 를 물을 수 없다.
    const tree = group([row({ ...SECC })])
    expect(tree.materials[0]).not.toHaveProperty('alias')
    expect(tree.materials[0].spec_thickness).toBe(1)
  })

  it('꺼진 열의 값은 보내지 않는다', () => {
    // 시료 칸을 껐는데 예전에 적어 둔 값이 함께 나가면, 사람은 만들지 않기로
    // 한 것이 만들어진 것을 나중에 안다.
    const visible = COLUMNS.filter((column) => column.group === 'material')
    const tree = group([row({ ...SECC, 'sample.lot_no': 'LOT-A' })], visible)
    expect(tree.materials[0].samples).toEqual([])
  })

  it('갈래는 켜져 있어도 꺼진 칸은 안 보낸다', () => {
    // 로트번호는 켜 두고 시료 별칭만 껐을 때. 갈래째 껐을 때와 달리 여기서는
    // 시료가 실제로 만들어지므로, **꺼진 칸이 조용히 따라가면 그대로 저장된다.**
    const visible = COLUMNS.filter((column) => column.key !== 'sample.alias')
    const tree = group(
      [row({ ...SECC, 'sample.lot_no': 'LOT-A', 'sample.alias': '안 보이는 값' })],
      visible
    )
    const sample = tree.materials[0].samples?.[0]
    expect(sample?.lot_no).toBe('LOT-A')
    expect(sample).not.toHaveProperty('alias')
  })

  it('몇 개가 만들어질지 센다', () => {
    const rows = [
      row({ ...SECC, 'sample.lot_no': 'LOT-A', 'specimen.orientation': 'MD' }),
      row({ 'specimen.orientation': 'TD' }),
      row({ 'material.family': 'Metal', 'material.category': 'Steel', 'material.grade': 'SGCC' }),
    ]
    expect(tally(group(rows), rows)).toEqual({
      materials: 2,
      samples: 1,
      specimens: 2,
      implied: 0,
    })
  })
})

describe('흠 짚기', () => {
  it('빈 줄은 짚지 않는다', () => {
    // 빈 줄을 그려 두는 것이 이 표의 방식이다. 그것을 흠이라 하면 늘 빨갛다.
    expect(problems(blankRows(5))).toEqual({})
  })

  it('Grade·Family·Category 가 없으면 짚는다', () => {
    const found = problems([row({ 'material.details': 'MDOI' })])[0]
    expect(found['material.grade']).toMatch(/Grade/)
    expect(found['material.family']).toMatch(/Family/)
    expect(found['material.category']).toMatch(/Category/)
  })

  it('숫자가 아니면 짚는다', () => {
    // **조용히 지나가면 안 된다.** `NaN` 이 서버로 가고, 거기서 나는 오류는
    // 어느 줄 때문인지 말해 주지 않는다.
    const found = problems([row({ ...SECC, 'material.spec_thickness': '두꺼움' })])
    expect(found[0]['material.spec_thickness']).toMatch(/숫자/)
  })

  it('푸아송비는 서버와 같은 범위다', () => {
    // 0.5 는 완전 비압축이라 풀리지 않는다.
    expect(problems([row({ ...SECC, 'material.poisson_ratio': '0.5' })])[0]).toBeTruthy()
    expect(problems([row({ ...SECC, 'material.poisson_ratio': '0.3' })])[0]).toBeUndefined()
  })

  it('방향은 서버가 아는 것만 받는다', () => {
    // 서버가 `MD, TD, DD, NA 중 하나` 로 막는데, 스무 줄을 보내고 나서
    // 알기에는 늦다.
    const bad = problems([row({ ...SECC, 'specimen.orientation': '옆으로' })])
    expect(bad[0]['specimen.orientation']).toMatch(/MD/)
    expect(problems([row({ ...SECC, 'specimen.orientation': 'md' })])[0]).toBeUndefined()
  })

  it('제조일 모양을 짚는다', () => {
    expect(problems([row({ ...SECC, 'sample.production_date': '2026/08/25' })])[0]).toBeTruthy()
    expect(
      problems([row({ ...SECC, 'sample.production_date': '2026-08-25' })])[0]
    ).toBeUndefined()
  })

  it('첫 줄에 재료가 없으면 짚는다', () => {
    // 붙일 재료가 없는 시료는 만들 수 없다.
    expect(problems([row({ 'sample.lot_no': 'LOT-A' })])[0]).toBeTruthy()
  })

  it('딸린 것 없이 이름만 겹치면 짚는다', () => {
    // 안 짚으면 앞줄은 만들어지고 뒷줄만 「이미 있습니다」로 막히는데, 사람은
    // 자기가 방금 만든 것과 부딪힌 줄 모르고 이미 있던 재료라고 읽는다.
    const two = [row({ ...SECC }), row({ ...SECC, 'material.grade': 'secc' })]
    expect(problems(two)[0]).toBeUndefined()
    expect(problems(two)[1]['material.grade']).toMatch(/1번 줄/)
  })

  it('시료가 붙어 있으면 같은 이름을 짚지 않는다', () => {
    // **이 표의 쓰임 자체다** — 같은 재료 아래에 시료를 더 넣는 것. 그것까지
    // 빨갛게 칠하면 기능이 막힌다.
    const two = [
      row({ ...SECC, 'sample.lot_no': 'LOT-A' }),
      row({ ...SECC, 'sample.lot_no': 'LOT-B' }),
    ]
    expect(problems(two)).toEqual({})
  })

  it('꺼진 열은 짚지 않는다', () => {
    const visible = COLUMNS.filter((column) => column.group === 'material')
    const rows = [row({ ...SECC, 'specimen.orientation': '옆으로' })]
    expect(problems(rows, visible)).toEqual({})
  })
})

describe('이어받는 칸', () => {
  it('분류를 위 재료에서 이어받는다', () => {
    // Grade 열에만 스무 줄을 붙여 넣는 것이 실제 작업이다. 줄마다 분류를 다시
    // 적게 하면 **오타 하나가 분류를 갈라 놓는다.**
    const rows = carried([row({ ...SECC }), row({ 'material.grade': 'SGCC' })])
    expect(rows[1]['material.family']).toBe('Metal')
    expect(rows[1]['material.category']).toBe('Steel')
  })

  it('이름을 만드는 값은 이어받지 않는다', () => {
    // 이어지면 같은 재료가 두 줄이 되고, 둘째 줄은 「이미 있습니다」로 막힌다.
    const rows = carried([row({ ...SECC }), row({ 'material.grade': 'SGCC' })])
    expect(rows[1]['material.details']).toBe('')
    expect(rows[1]['material.spec_thickness']).toBe('')
  })

  it('재료 칸이 없는 줄에는 채우지 않는다', () => {
    // 채우면 시료만 적은 줄이 새 재료가 된다.
    const rows = carried([row({ ...SECC }), row({ 'sample.lot_no': 'LOT-B' })])
    expect(rows[1]['material.family']).toBe('')
  })

  it('이어받은 값으로 흠이 사라진다', () => {
    const rows = carried([row({ ...SECC }), row({ 'material.grade': 'SGCC' })])
    expect(problems(rows)).toEqual({})
  })
})

describe('보내는 값', () => {
  it('단위를 값과 함께 항상 명시한다', () => {
    // 생략하면 "이 값이 mm 였나 m 였나" 를 나중에 아무도 답할 수 없다.
    const tree = group([
      row({ ...SECC, 'sample.lot_no': 'LOT-A', 'specimen.orientation': 'MD' }),
    ])
    const material = tree.materials[0]
    expect(material.spec_thickness_unit).toBe('mm')
    expect(material.density_unit).toBe('kg/m3')
    expect(material.samples?.[0].density_unit).toBe('kg/m3')
    expect(material.samples?.[0].specimens?.[0].length_unit).toBe('mm')
  })

  it('방향은 대문자로 보낸다', () => {
    // 서버는 대문자만 받는다. 사람이 소문자로 적는 것을 막을 이유는 없다.
    const tree = group([row({ ...SECC, 'specimen.orientation': 'md' })])
    expect(tree.materials[0].samples?.[0].specimens?.[0].orientation).toBe('MD')
  })
})
