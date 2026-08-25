/**
 * 여러 줄을 재료로 읽는다.
 *
 * **엑셀에서 붙여 넣으면 탭이 온다.** 그것을 안 받으면 사람은 한 줄이 통째로
 * Grade 가 된 것을 보고서야 안다 — 그때는 이미 스무 개를 잘못 만든 뒤다.
 */

import { describe, expect, it } from 'vitest'

import { parseRows } from '@/modules/materials/BulkMaterialDialog'

describe('여러 줄 읽기', () => {
  it('쉼표로 나눈다', () => {
    expect(parseRows('SECC, MDOI, 1.0')).toEqual([
      { grade: 'SECC', details: 'MDOI', thickness: 1, problem: undefined },
    ])
  })

  it('탭으로도 나눈다', () => {
    // 엑셀에서 그대로 붙여 넣는 것이 실제 작업이다.
    expect(parseRows('SGCC\tMDOI\t1.2')[0]).toMatchObject({
      grade: 'SGCC',
      details: 'MDOI',
      thickness: 1.2,
    })
  })

  it('빈 줄은 넘긴다', () => {
    // 붙여 넣기 끝에 빈 줄이 남는 것이 보통이다.
    expect(parseRows('SECC, , 1.0\n\n  \nSPCC, , 0.8')).toHaveLength(2)
  })

  it('가운데가 비어도 읽는다', () => {
    expect(parseRows('SPCC, , 0.8')[0]).toMatchObject({ grade: 'SPCC', details: '' })
  })

  it('두께가 없으면 비운다', () => {
    // **0 으로 채우지 않는다.** 두께 0 인 재료가 된다.
    expect(parseRows('SECC')[0].thickness).toBeNull()
  })

  it('Grade 가 없으면 짚는다', () => {
    expect(parseRows(', MDOI, 1.0')[0].problem).toMatch(/Grade/)
  })

  it('두께가 숫자가 아니면 짚는다', () => {
    // **조용히 지나가면 안 된다.** `NaN` 이 서버로 가고, 거기서 나는 오류는
    // 어느 줄 때문인지 말해 주지 않는다.
    expect(parseRows('SECC, MDOI, 두꺼움')[0].problem).toMatch(/숫자/)
  })
})
