/**
 * 표준 인장 처리 단계.
 *
 * **순서가 곧 규칙이다.** 이 시험들은 그 순서에 이유가 있다는 것을 잡아 둔다 —
 * 자리를 바꾸면 조용히 틀리는 것이 아니라 아예 안 돈다.
 */

import { describe, expect, it } from 'vitest'

import { missingSteps } from '@/modules/processing/gaps'
import {
  TENSILE_STANDARD,
  TENSILE_STARTER,
  missingStandard,
} from '@/modules/processing/standard'

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

describe('처음 열면 깔리는 순서', () => {
  const plugins = TENSILE_STARTER.map((one) => one.plugin)
  const at = (plugin: string) => plugins.indexOf(plugin)

  it('진응력까지 간다 — 여기서 끊으면 카드로 못 간다', () => {
    // 솔버 덱이 요구하는 것은 공칭이 아니라 진응력-진소성변형률이다
    // (`matcore/export`). 없으면 채택해도 결과 화면이 「채택된 결과에 진응력
    // 열이 없습니다」 로 되돌려 보낸다 — 처음 여는 사람이 거기서 막힌다.
    expect(plugins).toContain('tensile.true_plastic')
  })

  it('네킹에서 자른 뒤에 진응력을 낸다', () => {
    // **자르기가 먼저다.** 네킹이 시작되면 단면이 한 곳으로 몰려 「길이 변화로
    // 단면을 안다」 는 가정이 깨진다 — 자르지 않고 변환하면 그럴듯한 숫자가
    // 나오지만 틀렸다는 신호가 어디에도 없다.
    expect(at('tensile.necking_candidate')).toBeLessThan(at('curve.crop'))
    expect(at('curve.crop')).toBeLessThan(at('tensile.true_plastic'))
  })

  it('탄성계수를 먼저 내고 그것으로 진소성을 뺀다', () => {
    // 진소성변형률은 전체 변형률에서 탄성분을 뺀 것이라 E 가 있어야 한다.
    expect(at('tensile.elastic_modulus')).toBeLessThan(at('tensile.true_plastic'))
  })

  it('표준이 아는 순서를 어기지 않는다', () => {
    // 시작 순서는 표준의 부분집합이어야 한다 — 둘이 다른 차례를 말하면 어느
    // 쪽이 옳은지 화면에서 알 수 없다.
    // **차례만 본다.** 표준에는 같은 플러그인이 두 번 나오는 자리가 있어
    // (`curve.sort_unique`), 목록을 통째로 견주면 그 중복 때문에 어긋난다.
    const standard = TENSILE_STANDARD.map((one) => one.plugin)
    const ranks = plugins
      .map((one) => standard.indexOf(one))
      .filter((rank) => rank >= 0)
    const sorted = [...ranks].sort((a, b) => a - b)
    expect(ranks).toEqual(sorted)
  })
})
