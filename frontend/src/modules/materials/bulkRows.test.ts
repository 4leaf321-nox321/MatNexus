/**
 * 표에 붙여 넣고, 흠을 짚는다.
 *
 * **엑셀에서 붙여 넣으면 탭이 온다.** 그것을 안 받으면 사람은 한 줄이 통째로
 * Grade 가 된 것을 보고서야 안다 — 그때는 이미 스무 개를 잘못 만든 뒤다.
 */

import { describe, expect, it } from 'vitest'

import { COLUMNS, blankRows, isEmpty, paste, problems, spreads } from '@/modules/materials/bulkRows'

const AT = (key: string) => COLUMNS.findIndex((column) => column.key === key)

describe('붙여 넣기', () => {
  it('탭으로 나눈다', () => {
    // 엑셀에서 그대로 붙여 넣는 것이 실제 작업이다.
    const rows = paste(blankRows(2), 'SECC\tMDOI\t1.0', 0, 0)
    expect(rows[0]).toMatchObject({ grade: 'SECC', details: 'MDOI', spec_thickness: '1.0' })
  })

  it('탭이 없으면 쉼표로 나눈다', () => {
    const rows = paste(blankRows(2), 'SGCC, MDOI, 1.2\nSPCC, , 0.8', 0, 0)
    expect(rows[0]).toMatchObject({ grade: 'SGCC', spec_thickness: '1.2' })
    expect(rows[1]).toMatchObject({ grade: 'SPCC', details: '', spec_thickness: '0.8' })
  })

  it('탭이 있으면 쉼표는 값의 일부다', () => {
    // `1,000` 이 두 칸으로 갈라지면 안 된다.
    const rows = paste(blankRows(1), 'SECC\t1,000', 0, 0)
    expect(rows[0].details).toBe('1,000')
  })

  it('줄이 모자라면 늘린다', () => {
    // **안 늘리면 나머지가 조용히 사라진다.** 사람은 20줄을 붙여 넣고 5건만
    // 만들어진 것을 나중에 목록에서 안다.
    const rows = paste(blankRows(2), 'A\nB\nC\nD', 0, 0)
    expect(rows).toHaveLength(4)
    expect(rows[3].grade).toBe('D')
  })

  it('짚은 칸부터 채운다', () => {
    const rows = paste(blankRows(1), '7850\t0.3', 0, AT('density'))
    expect(rows[0]).toMatchObject({ grade: '', density: '7850', poisson_ratio: '0.3' })
  })

  it('표보다 넓으면 넘치는 칸은 버린다', () => {
    // 다음 줄로 밀면 값이 엉뚱한 칸에 들어가고, 그 편이 훨씬 알아채기 어렵다.
    const rows = paste(blankRows(1), '0.3\t넘침', 0, AT('poisson_ratio'))
    expect(rows).toHaveLength(1)
    expect(rows[0].poisson_ratio).toBe('0.3')
  })

  it('빈 줄은 넘긴다', () => {
    // 붙여 넣기 끝에 빈 줄이 남는 것이 보통이다.
    expect(paste(blankRows(1), 'A\n\n  \nB', 0, 0).filter((row) => !isEmpty(row))).toHaveLength(2)
  })

  it('한 칸짜리는 글자 그대로 둔다', () => {
    // 별칭에 `도어 이너, 아우터` 를 붙여 넣었는데 두 칸으로 갈라지면 안 된다.
    expect(spreads('도어 이너, 아우터')).toBe(false)
    expect(spreads('SECC\tMDOI')).toBe(true)
    expect(spreads('SECC\nSGCC')).toBe(true)
  })
})

describe('흠 짚기', () => {
  const row = (values: Record<string, string>) => ({ ...blankRows(1)[0], ...values })

  it('빈 줄은 짚지 않는다', () => {
    // 빈 줄을 그려 두는 것이 이 표의 방식이다. 그것을 흠이라 하면 늘 빨갛다.
    expect(problems(blankRows(5))).toEqual({})
  })

  it('Grade 가 없으면 짚는다', () => {
    expect(problems([row({ details: 'MDOI' })])[0].grade).toMatch(/Grade/)
  })

  it('숫자가 아니면 짚는다', () => {
    // **조용히 지나가면 안 된다.** `NaN` 이 서버로 가고, 거기서 나는 오류는
    // 어느 줄 때문인지 말해 주지 않는다.
    expect(problems([row({ grade: 'SECC', spec_thickness: '두꺼움' })])[0].spec_thickness).toMatch(
      /숫자/
    )
  })

  it('두께 0 을 막는다', () => {
    expect(problems([row({ grade: 'SECC', spec_thickness: '0' })])[0].spec_thickness).toBeTruthy()
  })

  it('푸아송비는 서버와 같은 범위다', () => {
    // 0.5 는 완전 비압축이라 풀리지 않는다.
    expect(problems([row({ grade: 'SECC', poisson_ratio: '0.5' })])[0].poisson_ratio).toBeTruthy()
    expect(problems([row({ grade: 'SECC', poisson_ratio: '0.3' })])[0]).toBeUndefined()
  })

  it('같은 이름이 될 줄을 짚는다', () => {
    // 안 짚으면 앞줄은 만들어지고 뒷줄만 「이미 있습니다」로 막히는데, 사람은
    // 자기가 방금 만든 것과 부딪힌 줄 모르고 이미 있던 재료라고 읽는다.
    const two = [
      row({ grade: 'SECC', details: 'MDOI', spec_thickness: '1.0' }),
      row({ grade: 'secc', details: 'MDOI', spec_thickness: '1.0' }),
    ]
    expect(problems(two)[0]).toBeUndefined()
    expect(problems(two)[1].grade).toMatch(/1번 줄/)
  })

  it('두께가 다르면 다른 이름이다', () => {
    const two = [
      row({ grade: 'SECC', spec_thickness: '1.0' }),
      row({ grade: 'SECC', spec_thickness: '1.2' }),
    ]
    expect(problems(two)).toEqual({})
  })
})
