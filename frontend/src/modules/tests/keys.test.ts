/**
 * 채널 키 규칙 — **서버가 거절할 값을 만들어 보내지 않는다.**
 *
 * 같은 규칙을 두 화면이 각자 구현하고 있었고 둘이 달랐다. 프로파일 편집기 쪽은
 * 숫자로 시작하는 키를 만들어서, 저장할 때 422 를 받고 사용자는 왜 거절됐는지
 * 알 수 없었다.
 */

import { describe, expect, it } from 'vitest'

import { isValidChannelKey, toChannelKey } from '@/modules/tests/keys'

describe('toChannelKey', () => {
  it('소문자·밑줄로 바꾼다', () => {
    expect(toChannelKey('Storage modulus')).toBe('storage_modulus')
    expect(toChannelKey('Tan(delta)')).toBe('tan_delta')
    expect(toChannelKey('DMA')).toBe('dma')
  })

  it('숫자로 시작하면 그 숫자를 뗀다', () => {
    // **실재하는 열 이름이다.** DMA 의 TTS 마스터 곡선에 `1/temperature` 가 있다.
    // 떼지 않으면 `1_temperature` 가 되어 서버가 422 로 거절한다.
    expect(toChannelKey('1/temperature')).toBe('temperature')
    expect(toChannelKey('2nd modulus')).toBe('nd_modulus')
  })

  it('만들어진 키는 서버 규칙을 지킨다', () => {
    const names = [
      'Angular frequency',
      'Tan(delta)',
      '1/temperature',
      'Complex compliance',
      'Phase angle',
      'aT (x variable)',
      '  Storage  modulus  ',
    ]
    for (const name of names) {
      expect(isValidChannelKey(toChannelKey(name))).toBe(true)
    }
  })

  it('만들 수 없는 이름은 빈 값을 준다', () => {
    // 화면이 이것을 보고 "키를 정하세요" 라고 물어야 한다. 아무 값이나 지어내
    // 보내면 거절당하고, 그때 이유를 설명할 수 없다.
    expect(toChannelKey('1/2')).toBe('')
    expect(toChannelKey('...')).toBe('')
    expect(isValidChannelKey('')).toBe(false)
  })

  it('밑줄이 겹치거나 끝에 남지 않는다', () => {
    expect(toChannelKey('Force  (max)')).toBe('force_max')
    expect(toChannelKey('Load___')).toBe('load')
  })
})
