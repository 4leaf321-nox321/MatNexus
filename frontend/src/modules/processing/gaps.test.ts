import { describe, expect, it } from 'vitest'

import { missingSteps } from '@/modules/processing/gaps'

const step = (plugin: string, options: Record<string, unknown> = {}) => ({ plugin, options })

describe('missingSteps', () => {
  it('공칭까지만 하는 레시피는 진응력과 재샘플을 짚는다', () => {
    // 사용자가 실제로 쓴 구성이다. 이 구성으로 처리하면 CAE 카드도 대표 곡선도
    // 못 만드는데, 그 사실은 세 화면 건너에서야 드러났다.
    const found = missingSteps([
      step('tensile.engineering'),
      step('curve.sort_unique', { x: 'strain_engineering' }),
      step('tensile.strength'),
    ])
    expect(found.map((gap) => gap.plugin)).toEqual(['tensile.true_plastic', 'curve.resample'])
    // 진소성 열을 안 만드는 구성이므로 **그 축의 재샘플은 안 묻는다.**
    expect(found.filter((gap) => gap.axis === 'strain_true_plastic')).toEqual([])
  })

  it('두 축을 다 다듬으면 아무것도 안 짚는다', () => {
    expect(
      missingSteps([
        step('tensile.engineering'),
        step('curve.resample', { x: 'strain_engineering' }),
        step('tensile.true_plastic'),
        step('curve.resample', { x: 'strain_true_plastic' }),
      ])
    ).toEqual([])
  })

  it('공칭 축 재샘플 하나로 진소성 축까지 있다고 하지 않는다', () => {
    // **이 시험이 이 파일의 요점이다.** 전에는 플러그인 이름만 봐서, 공칭 축에
    // 하나 있으면 진소성 축이 비어도 아무 말 안 했다 — 그러면 덱으로 내보낼 때
    // 가서야 드러난다.
    const found = missingSteps([
      step('tensile.engineering'),
      step('curve.resample', { x: 'strain_engineering' }),
      step('tensile.true_plastic'),
    ])
    expect(found).toHaveLength(1)
    expect(found[0].axis).toBe('strain_true_plastic')
  })

  it('진소성 축만 다듬으면 공칭 축을 짚는다', () => {
    const found = missingSteps([
      step('tensile.true_plastic'),
      step('curve.resample', { x: 'strain_true_plastic' }),
    ])
    expect(found).toHaveLength(1)
    expect(found[0].axis).toBe('strain_engineering')
  })
})
