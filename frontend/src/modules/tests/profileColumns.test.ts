/**
 * 열 규칙의 왕복 — **읽고 다시 쓰면 같은 것이 나와야 한다.**
 *
 * 이 시험이 없어서, 편집 화면에서 기본 프로파일을 열고 저장만 눌러도 단위와
 * `skip` 이 사라지는 것을 아무도 못 잡았다.
 */

import { describe, expect, it } from 'vitest'

import type { ProfileDefinition } from '@/modules/tests/api'
import {
  readColumnRules,
  unitBlocking,
  unitState,
  writeColumnRules,
} from '@/modules/tests/profileColumns'

/** `legacy_profiles.py` 의 `legacy_mtet` 이 실제로 갖고 있는 열 규칙. */
const LEGACY: NonNullable<ProfileDefinition['columns']> = {
  '#': { skip: true },
  'Standard extensometer (mm)': { channel: 'displacement', unit: 'mm' },
  'Standard extensometer': { channel: 'displacement', unit: 'mm' },
  'Standard load cell (N)': { channel: 'force', unit: 'N' },
  'Specimen width (mm)': { channel: 'specimen_width', unit: 'mm' },
}

describe('왕복', () => {
  it('기본 프로파일을 읽어 그대로 다시 쓰면 같다', () => {
    // **아무것도 안 고치고 저장만 눌러도** 정의가 바뀌면 안 된다.
    expect(writeColumnRules(readColumnRules(LEGACY))).toEqual(LEGACY)
  })

  it('버릴 열은 배타다', () => {
    // `profile.py` 가 `skip` 에서 바로 넘어가므로 채널을 함께 적으면 아무도 안
    // 보는 죽은 글자가 된다.
    const written = writeColumnRules({
      '#': { channel: 'force', unit: 'N', skip: true },
    })
    expect(written['#']).toEqual({ skip: true })
  })

  it('단위를 안 적었으면 안 적는다', () => {
    // 빈 문자열을 적으면 옛 정의와 모양이 달라져 쓸데없는 리비전이 생긴다.
    const written = writeColumnRules({ Force: { channel: 'force', unit: '', skip: false } })
    expect(written.Force).toEqual({ channel: 'force' })
  })

  it('아무것도 안 정한 열은 아예 안 적는다', () => {
    const written = writeColumnRules({ 무엇: { channel: '', unit: '', skip: false } })
    expect(written).toEqual({})
  })

  it('채널 없이 단위만 적은 것도 지킨다', () => {
    // 채널을 안 정해도 단위는 뜻이 있다 — 나중에 채널을 붙일 때 그대로 쓴다.
    const written = writeColumnRules({ 무엇: { channel: '', unit: 'MPa', skip: false } })
    expect(written.무엇).toEqual({ unit: 'MPa' })
  })

  it('채널이 없는 규칙을 읽어도 안 터진다', () => {
    // 타입은 `channel: string` 이라고 단언했지만 저장된 데이터에는 없다.
    expect(readColumnRules({ '#': { skip: true } })['#']).toEqual({
      channel: '',
      unit: '',
      skip: true,
    })
  })
})

describe('단위 상태', () => {
  it('빈 칸과 단위 줄 없음을 가른다', () => {
    // **둘은 전혀 다르다.** 빈 칸은 무차원으로 읽히고, 없음은 등록이 거부된다.
    // 화면이 둘 다 `—` 로 그려서 저장탄성률이 무차원으로 읽힌 사고가 났다.
    expect(unitState({ unit: '', raw: '', symbol: '1' })).toBe('blank')
    expect(unitState({ unit: '', raw: undefined, symbol: undefined })).toBe('absent')
  })

  it('프로파일이 적은 것이 파일을 이긴다', () => {
    expect(unitState({ unit: 'MPa', raw: 'kPa', symbol: 'kPa' })).toBe('profile')
  })

  it('파일 표기를 서버가 알아본 것과 모르는 것을 가른다', () => {
    expect(unitState({ unit: '', raw: 'Mpa', symbol: 'MPa' })).toBe('file')
    expect(unitState({ unit: '', raw: 'furlong', symbol: null })).toBe('unknown')
  })

  it('이 파일에 없는 열은 판정하지 않는다', () => {
    // 저장본에만 있는 열을 '단위 없음' 이라고 하면, 다른 파일로 만든 프로파일을
    // 열 때마다 있지도 않은 문제가 뜬다.
    expect(unitState({ unit: '', raw: undefined, symbol: undefined, inFile: false })).toBe(
      'unjudged'
    )
  })
})

describe('저장 전에 막을 것', () => {
  it('채널로 정했는데 단위를 모르면 막는다', () => {
    const rule = { channel: 'force', unit: '', skip: false }
    expect(unitBlocking('absent', rule)).toBe(true)
    expect(unitBlocking('unknown', rule)).toBe(true)
  })

  it('안 정한 열과 버릴 열은 안 막는다', () => {
    // 매핑 안 한 열은 정의된 채널이 아니라 계산에 안 쓰인다 — 막을 이유가 없다.
    expect(unitBlocking('absent', { channel: '', unit: '', skip: false })).toBe(false)
    expect(unitBlocking('absent', { channel: 'force', unit: '', skip: true })).toBe(false)
  })

  it('빈 칸은 안 막는다', () => {
    // 무차원으로 읽히는 것은 뜻이 있는 해석이다. 경고는 하되 저장은 막지 않는다 —
    // 실제로 무차원인 열(Tan delta)이 있다.
    expect(unitBlocking('blank', { channel: 'tan_delta', unit: '', skip: false })).toBe(false)
  })

  it('이 파일에 없는 열은 안 막는다', () => {
    expect(unitBlocking('unjudged', { channel: 'force', unit: '', skip: false })).toBe(false)
  })
})
