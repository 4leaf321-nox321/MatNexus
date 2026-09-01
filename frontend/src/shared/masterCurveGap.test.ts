/**
 * 「아직 안 겹친 시험」 을 **맞게 세는가.**
 *
 * 이 수가 틀리면 화면이 **할 수 없는 일을 재촉한다.** 변형률 스윕은 온도가 한 단
 * 이라 겹칠 것이 없는데, 시험종류 키로는 주파수-온도 스윕과 구별되지 않는다.
 * 한 번 헛된 재촉을 하면 사람은 그 줄을 다시 안 읽는다.
 */

import { describe, expect, it } from 'vitest'

import { masterCurveGap } from '@/shared/masterCurveGap'
import type { GapRun } from '@/shared/masterCurveGap'

const run = (over: Partial<GapRun> = {}): GapRun => ({
  test_type_key: 'dma_sweep',
  master_curve_count: 0,
  temperature_step_count: 6,
  ...over,
})

describe('무엇을 남은 일로 세나', () => {
  it('마스터커브가 있으면 준비된 것으로 센다', () => {
    expect(masterCurveGap([run({ master_curve_count: 1 })], [])).toMatchObject({
      ready: 1,
      pending: 0,
    })
  })

  it('온도가 여러 단인데 안 겹쳤으면 남은 일이다', () => {
    expect(masterCurveGap([run()], [])).toMatchObject({ pending: 1, cannot: 0 })
  })

  it('온도가 한 단이면 남은 일이 아니다', () => {
    // **변형률 스윕.** 겹칠 상대가 없다 — 재촉하면 할 수 없는 일을 시키는 것이다.
    expect(masterCurveGap([run({ temperature_step_count: 1 })], [])).toMatchObject({
      pending: 0,
      cannot: 1,
    })
  })

  it('안 세어 본 것은 남은 일에도 못 하는 것에도 넣지 않는다', () => {
    // `null` 은 「이 칸이 생기기 전에 읽은 시험」 이다. 「할 수 있다」 로 세면 없는
    // 일을 만들고, 「할 수 없다」 로 세면 진짜 남은 일을 숨긴다.
    const gap = masterCurveGap([run({ temperature_step_count: null })], [])
    expect(gap).toMatchObject({ pending: 0, cannot: 0, unknown: 1 })
  })
})

describe('어느 시험을 보나', () => {
  it('키가 맞는 것만 센다', () => {
    const rows = [run(), run({ test_type_key: 'tensile' })]
    expect(masterCurveGap(rows, ['dma_sweep'])).toMatchObject({ pending: 1 })
  })

  it('부서가 만든 종류도 목록에 있으면 센다', () => {
    // 서버가 `applies_to` 를 **풀어서** 준다 — 채널이 맞으면 키가 달라도 들어온다.
    const rows = [run({ test_type_key: 'dma_inhouse_freqtemp' })]
    expect(masterCurveGap(rows, ['dma_sweep', 'dma_inhouse_freqtemp'])).toMatchObject({
      pending: 1,
    })
  })

  it('목록이 비면 제한 없이 센다', () => {
    // 모달 안에서는 이미 종류로 걸러 둔 목록을 넘긴다 — 거기서 또 거르면 두 번
    // 거르게 되고, 한쪽 규칙이 바뀌면 수가 갈린다.
    expect(masterCurveGap([run({ test_type_key: '무엇이든' })], [])).toMatchObject({
      pending: 1,
    })
  })
})
