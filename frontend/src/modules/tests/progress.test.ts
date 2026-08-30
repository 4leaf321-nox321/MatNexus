/**
 * 진행 띠가 **다음에 할 일을 맞게 말하는가.**
 *
 * 이 문장이 틀리면 사람은 엉뚱한 탭으로 간다. 특히 두 가지가 조용히 틀린다 —
 * 결과를 저장만 하고 채택을 안 한 것을 「됨」 으로 보는 것, 그리고 점탄성을
 * 했다고 값 내기까지 된 것처럼 보이는 것.
 */

import { describe, expect, it } from 'vitest'

import { runProgress } from '@/modules/tests/progress'
import type { RunState } from '@/modules/tests/progress'

const BASE: RunState = {
  status: 'parsed',
  resultCount: 0,
  adopted: false,
  curveCount: 1,
  viscoelastic: false,
  masterCurveCount: 0,
  pronyFitCount: 0,
}

const step = (state: Partial<RunState>, key: string) => {
  const found = runProgress({ ...BASE, ...state }).find((one) => one.key === key)
  if (!found) throw new Error(`${key} 단계가 없습니다`)
  return found
}

describe('아직 안 읽힌 시험', () => {
  it('진행 띠를 안 그린다', () => {
    // 읽는 중에는 할 수 있는 일이 없다. 「처리하러 가기」 를 띄우면 눌러도
    // 꺼진 탭이라 아무 일이 안 일어난다.
    expect(runProgress({ ...BASE, status: 'pending' })).toEqual([])
    expect(runProgress({ ...BASE, status: 'failed' })).toEqual([])
  })
})

describe('값 내기', () => {
  it('결과가 없으면 처리로 보낸다', () => {
    expect(step({}, 'results').go?.tab).toBe('process')
  })

  it('저장만 하고 채택을 안 했으면 「됨」 이 아니다', () => {
    // **여기가 조용히 빠지는 자리다.** 통계는 채택된 것만 세는데, 저장한 사람은
    // 다 했다고 여긴다.
    const one = step({ resultCount: 3 }, 'results')
    expect(one.done).toBe(false)
    expect(one.now).toMatch(/채택/)
    expect(one.go?.tab).toBe('results')
  })

  it('채택하면 어디로 갔는지 말한다', () => {
    const one = step({ resultCount: 3, adopted: true }, 'results')
    expect(one.done).toBe(true)
    expect(one.now).toMatch(/물성 표/)
  })
})

describe('점탄성', () => {
  it('점탄성이 아니면 그 칸이 아예 없다', () => {
    // 인장 시험에 「겹치세요」 가 뜨면 할 수 없는 일을 남은 일로 읽는다.
    expect(runProgress(BASE).some((one) => one.key === 'viscoelastic')).toBe(false)
  })

  it('마스터커브가 없으면 겹치기부터 말한다', () => {
    const one = step({ viscoelastic: true }, 'viscoelastic')
    expect(one.done).toBe(false)
    expect(one.now).toMatch(/겹치거나/)
  })

  it('겹치기만 했으면 아직 「됨」 이 아니다', () => {
    const one = step({ viscoelastic: true, masterCurveCount: 2 }, 'viscoelastic')
    expect(one.done).toBe(false)
    expect(one.now).toMatch(/계수를 안 맞춤/)
  })

  it('적합까지 했으면 카드로 보낸다', () => {
    const one = step(
      { viscoelastic: true, masterCurveCount: 1, pronyFitCount: 2 },
      'viscoelastic'
    )
    expect(one.done).toBe(true)
    expect(one.now).toMatch(/카드로 만들면/)
  })

  it('점탄성을 했다고 값 내기가 되지 않는다', () => {
    // **두 경로에 선행 관계가 없다.** 한쪽의 진행이 다른 쪽을 채우면, 채택
    // 안 된 시험이 「다 됨」 으로 보이고 통계에서는 계속 빠진다.
    const state = {
      viscoelastic: true,
      masterCurveCount: 1,
      pronyFitCount: 1,
      resultCount: 2,
    }
    expect(step(state, 'viscoelastic').done).toBe(true)
    expect(step(state, 'results').done).toBe(false)
  })
})
