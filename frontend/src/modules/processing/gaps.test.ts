import { describe, expect, it } from 'vitest'

import { missingSteps } from '@/modules/processing/gaps'

describe('missingSteps', () => {
  it('공칭까지만 하는 레시피는 둘 다 짚는다', () => {
    // 사용자가 실제로 쓴 구성이다. 이 구성으로 처리하면 CAE 카드도 대표 곡선도
    // 못 만드는데, 그 사실은 세 화면 건너에서야 드러났다.
    const found = missingSteps(['tensile.engineering', 'curve.sort_unique', 'tensile.strength'])
    expect(found.map((gap) => gap.plugin)).toEqual([
      'tensile.true_plastic',
      'curve.resample',
    ])
  })

  it('둘 다 있으면 아무것도 안 짚는다', () => {
    expect(
      missingSteps(['tensile.engineering', 'curve.resample', 'tensile.true_plastic'])
    ).toEqual([])
  })

  it('하나만 빠지면 그 하나만', () => {
    const found = missingSteps(['tensile.true_plastic'])
    expect(found).toHaveLength(1)
    expect(found[0].plugin).toBe('curve.resample')
  })
})
