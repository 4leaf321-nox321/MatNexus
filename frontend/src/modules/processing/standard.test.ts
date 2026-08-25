/**
 * 표준 인장 처리 단계.
 *
 * **순서가 곧 규칙이다.** 이 시험들은 그 순서에 이유가 있다는 것을 잡아 둔다 —
 * 자리를 바꾸면 조용히 틀리는 것이 아니라 아예 안 돈다.
 */

import { describe, expect, it } from 'vitest'

import { missingSteps } from '@/modules/processing/gaps'
import { TENSILE_STANDARD, missingStandard } from '@/modules/processing/standard'

const at = (plugin: string) => TENSILE_STANDARD.findIndex((one) => one.plugin === plugin)
const last = (plugin: string) =>
  TENSILE_STANDARD.map((one) => one.plugin).lastIndexOf(plugin)

describe('표준 단계', () => {
  it('gaps 가 짚는 것을 빠짐없이 담는다', () => {
    // **말하는 것과 넣어 주는 것이 어긋나면 안 된다.** 경고만 뜨고 채워도
    // 그대로 뜨면, 사람은 무엇을 더 해야 하는지 모른다.
    const plugins = TENSILE_STANDARD.map((one) => one.plugin)
    expect(missingSteps(plugins)).toEqual([])
  })

  it('탄성계수가 그것을 쓰는 단계보다 앞에 있다', () => {
    // 항복강도와 진소성이 `@youngs_modulus` 로 그 값을 가리킨다 — 뒤에 있으면
    // 그 자리에서 "값이 필요합니다" 로 멈춘다.
    expect(at('tensile.elastic_modulus')).toBeLessThan(at('tensile.proof_stress'))
    expect(at('tensile.elastic_modulus')).toBeLessThan(at('tensile.true_plastic'))
  })

  it('네킹을 짚고 나서 자른다', () => {
    expect(at('tensile.necking_candidate')).toBeLessThan(at('curve.crop'))
  })

  it('자르고 나서 진소성을 낸다', () => {
    // **네킹을 지나면 진소성변형률이 되돌아온다.** 안 자르면 그 뒤가 단조
    // 증가가 아니라 재샘플도 적합도 못 한다.
    expect(at('curve.crop')).toBeLessThan(at('tensile.true_plastic'))
  })

  it('진소성을 낸 뒤 다시 정렬하고 재샘플한다', () => {
    expect(at('tensile.true_plastic')).toBeLessThan(last('curve.sort_unique'))
    expect(last('curve.sort_unique')).toBeLessThan(last('curve.resample'))
  })

  it('두 축을 모두 재샘플한다', () => {
    // 여러 시편의 평균을 내려면 격자가 같아야 하고, 축이 둘이다.
    const axes = TENSILE_STANDARD.filter((one) => one.plugin === 'curve.resample').map(
      (one) => one.options.x
    )
    expect(axes).toEqual(['strain_engineering', 'strain_true_plastic'])
  })

  it('재샘플의 끝은 비워 둔다', () => {
    // **지어내면 어떤 재료에서는 데이터를 잘라 버린다.** 묶음의 모든 시편이
    // 같은 값이어야 하는데 그 값은 가장 짧은 곡선이 정하고, 통계가 그때 어느
    // 값으로 고정하면 되는지 문장으로 말해 준다.
    for (const step of TENSILE_STANDARD.filter((one) => one.plugin === 'curve.resample')) {
      expect(step.options.start).toBe(0)
      expect(step.options).not.toHaveProperty('end')
    }
  })

  it('시편 치수와 앞 단계 값을 참조로 가리킨다', () => {
    // 사람이 손으로 옮겨 적으면 다시 쟀을 때 한쪽만 바뀐다.
    const first = TENSILE_STANDARD[0]
    expect(first.options.gauge_length).toBe('@specimen_gauge_length')
    expect(first.options.area).toBe('@specimen_area')
  })
})

describe('빠진 것만 채우기', () => {
  it('빈 목록에는 전부 넣는다', () => {
    expect(missingStandard([])).toHaveLength(TENSILE_STANDARD.length)
  })

  it('있는 것은 다시 안 넣는다', () => {
    // **통째로 갈아 끼우지 않는다.** 사람이 손댄 옵션을 말없이 되돌리면, 그
    // 사람은 자기가 정한 값이 사라진 것을 나중에 결과에서 안다.
    const added = missingStandard(['tensile.engineering', 'curve.sort_unique'])
    expect(added.map((one) => one.plugin)).not.toContain('tensile.engineering')
    expect(added.map((one) => one.plugin)).toContain('tensile.true_plastic')
  })

  it('돌려준 것을 고쳐도 원본이 안 바뀐다', () => {
    // 표를 그대로 넘기면 화면에서 옵션을 고칠 때 다음 사람 것까지 바뀐다.
    const added = missingStandard([])
    added[0].options.gauge_length = '엉뚱한 값'
    expect(TENSILE_STANDARD[0].options.gauge_length).toBe('@specimen_gauge_length')
  })
})
