/**
 * 곡선 고르기 — **실제로 났던 결함 둘을 여기서 잡는다.**
 *
 *   1. 곡선을 바꿨는데 축이 그대로 → "이 시험에 없는 채널입니다: step_time"
 *   2. 축 선택지를 정의에서 뽑아 → 처리결과 곡선을 아예 그릴 수 없었다
 *
 * 둘 다 사용자가 화면에서 발견했다. 화면 안에 로직이 있어서 시험할 수 없었다.
 */

import { describe, expect, it } from 'vitest'

import {
  axisOptionsFor,
  groupCurveFamilies,
  memberLabel,
  resolveAxes,
} from '@/modules/tests/curves'
import type { CurveLike } from '@/modules/tests/curves'

/** 실측 그대로 — TA DMA850 주파수-온도 스윕이 만드는 곡선 8벌. */
const CURVES: CurveLike[] = [
  ...Array.from({ length: 6 }, (_, index) => ({
    key: `temperature_sweep_multifrequency_${index + 2}`,
    label: `Temperature Sweep (Multifrequency) - ${index + 2}`,
    kind: 'measured',
    row_count: 8,
    // **첫 구간만 채널이 9개다.** 실측에서 그랬다.
    channels:
      index === 0
        ? ['angular_frequency', 'step_time', 'temperature', 'storage_modulus', 'frequency']
        : ['angular_frequency', 'step_time', 'temperature', 'storage_modulus'],
  })),
  {
    key: 'tts_master_curve_20_0_c',
    label: 'TTS - master curve (20.0 °C)',
    kind: 'derived',
    row_count: 7,
    channels: ['frequency', 'storage_modulus', 'complex_compliance', 'phase_angle'],
  },
  {
    key: 'tts_shift_factors',
    label: 'TTS - shift factors',
    kind: 'derived',
    row_count: 6,
    channels: ['temperature', 'at_x_variable'],
  },
]

const DECLARED = [
  { key: 'angular_frequency', label: '각주파수', si_unit: 'rad/s', dimension: 'angular_frequency' },
  { key: 'step_time', label: '구간 시간', si_unit: 's', dimension: 'time' },
  { key: 'temperature', label: '온도', si_unit: 'K', dimension: 'temperature' },
  { key: 'storage_modulus', label: '저장탄성률', si_unit: 'Pa', dimension: 'stress' },
]

describe('종류로 묶기', () => {
  it('일련번호가 다른 것을 한 종류로 본다', () => {
    const families = groupCurveFamilies(CURVES)
    const names = families.map((family) => family.name)
    expect(names).toEqual([
      'Temperature Sweep (Multifrequency)',
      'TTS - master curve (20.0 °C)',
      'TTS - shift factors',
    ])
    expect(families[0].items).toHaveLength(6)
  })

  it('채널 구성이 달라도 같은 종류로 묶는다', () => {
    // **채널로 묶으면 안 되는 이유.** 실측에서 첫 구간만 열이 9개였다 —
    // 채널 기준이면 `- 2` 만 따로 떨어져 나온다.
    const families = groupCurveFamilies(CURVES)
    const keys = families[0].items.map((item) => item.key)
    expect(keys).toContain('temperature_sweep_multifrequency_2')
    expect(keys).toContain('temperature_sweep_multifrequency_7')
  })

  it('종류에 성격을 붙인다', () => {
    const families = groupCurveFamilies(CURVES)
    expect(families[0].kind).toBe('measured')
    expect(families[1].kind).toBe('derived')
  })

  it('구간 이름은 종류를 뺀 나머지만 보여 준다', () => {
    // 같은 접두어를 여섯 번 반복해 봐야 다른 점이 안 보인다.
    expect(memberLabel(CURVES[0], 'Temperature Sweep (Multifrequency)')).toBe('2')
    expect(memberLabel(CURVES[5], 'Temperature Sweep (Multifrequency)')).toBe('7')
  })
})

describe('축 선택지', () => {
  it('그 곡선이 가진 채널만 준다', () => {
    // 정의에는 `step_time` 이 있지만 마스터 곡선에는 없다.
    const options = axisOptionsFor(CURVES[6], DECLARED).map((option) => option.key)
    expect(options).not.toContain('step_time')
    expect(options).toContain('frequency')
  })

  it('정의에 없는 채널도 고를 수 있다', () => {
    // **이게 없으면 처리결과 곡선을 그릴 방법이 아예 없다.**
    // `complex_compliance` 는 시험 종류 정의에 없다.
    const options = axisOptionsFor(CURVES[6], DECLARED)
    const compliance = options.find((option) => option.key === 'complex_compliance')
    expect(compliance).toBeDefined()
    // 정의가 없으면 키를 그대로 이름으로 쓴다 — 안 보여 주는 것보다 낫다.
    expect(compliance?.label).toBe('complex_compliance')
    expect(compliance?.si_unit).toBeNull()
  })

  it('정의가 있으면 이름과 단위를 보탠다', () => {
    const options = axisOptionsFor(CURVES[0], DECLARED)
    const temperature = options.find((option) => option.key === 'temperature')
    expect(temperature?.label).toBe('온도')
    expect(temperature?.si_unit).toBe('K')
    expect(temperature?.dimension).toBe('temperature')
  })
})

describe('곡선을 바꿀 때 축', () => {
  it('그 곡선에 없는 축이면 다시 고른다', () => {
    // 사용자가 실제로 만난 상황: 측정 곡선에서 `step_time` 을 보다가 마스터
    // 곡선으로 넘어가면 "이 시험에 없는 채널입니다: step_time".
    const axes = { x: 'step_time', y: 'storage_modulus' }
    const options = axisOptionsFor(CURVES[6], DECLARED)
    const next = resolveAxes(axes, options)
    expect(next).not.toBe(axes)
    expect(next).toEqual({ x: 'frequency', y: 'storage_modulus' })
  })

  it('둘 다 있으면 그대로 둔다', () => {
    // 고른 축을 멋대로 되돌리면 곡선을 넘길 때마다 처음으로 돌아간다.
    const axes = { x: 'temperature', y: 'storage_modulus' }
    const options = axisOptionsFor(CURVES[0], DECLARED)
    expect(resolveAxes(axes, options)).toBe(axes)
  })

  it('처음에는 앞의 둘을 고른다', () => {
    const options = axisOptionsFor(CURVES[0], DECLARED)
    expect(resolveAxes(null, options)).toEqual({
      x: 'angular_frequency',
      y: 'step_time',
    })
  })

  it('채널이 하나뿐이면 건드리지 않는다', () => {
    const single = axisOptionsFor(
      { ...CURVES[7], channels: ['temperature'] },
      DECLARED
    )
    expect(resolveAxes(null, single)).toBeNull()
  })
})
