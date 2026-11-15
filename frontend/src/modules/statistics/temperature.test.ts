/**
 * 묶음의 시험 온도 — 열쇠 · 같은 묶음 · 이름 꼬리(2026-11-15).
 *
 * 같은 종류 · 방향에 온도 묶음이 둘이면 열쇠가 겹쳐 펼침 상태 · 단추가 섞였다. 미기재는 상온이라고
 * 단정하지 않는다 — 이름에 온도를 안 붙인다.
 */

import { describe, expect, it } from 'vitest'

import {
  groupKey,
  hasTemperatureSiblings,
  sameGroup,
  temperatureSuffix,
  temperatureText,
} from '@/modules/statistics/temperature'

const room = { test_type_key: 'tensile', orientation: 'MD', temperature_k: 296.15 }
const hot = { test_type_key: 'tensile', orientation: 'MD', temperature_k: 353.15 }
const unknown = { test_type_key: 'tensile', orientation: 'MD', temperature_k: null }

describe('시험 온도 묶음', () => {
  it('온도를 °C 로 읽는다 — 미기재는 말로', () => {
    expect(temperatureText(353.15)).toBe('80 °C')
    expect(temperatureText(null)).toBe('온도 미기재')
    expect(temperatureSuffix(296.15)).toBe(' · 23 °C')
    expect(temperatureSuffix(null)).toBe('')
  })

  it('온도가 다르면 다른 묶음이다', () => {
    expect(groupKey(room)).not.toBe(groupKey(hot))
    expect(groupKey(unknown)).toBe(groupKey({ ...unknown, temperature_k: undefined }))
    expect(sameGroup(room, { ...room })).toBe(true)
    expect(sameGroup(room, hot)).toBe(false)
    expect(sameGroup(unknown, room)).toBe(false)
    expect(sameGroup(null, room)).toBe(false)
  })

  it('곁에 다른 온도의 묶음이 있을 때만 온도를 붙인다', () => {
    expect(hasTemperatureSiblings(room, [room, hot])).toBe(true)
    expect(hasTemperatureSiblings(room, [room])).toBe(false)
    expect(hasTemperatureSiblings(room, [room, { ...hot, orientation: 'TD' }])).toBe(false)
  })
})
