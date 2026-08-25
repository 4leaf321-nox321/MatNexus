/**
 * 참조는 **칸마다 최대 하나**여야 한다.
 *
 * 처음에는 단위로 골랐다 — `param.unit === 'm'` 인 것을 전부 후보로 냈다.
 * 그랬더니 '게이지 길이' 칸에 게이지 길이·폭·두께 셋이 붙었고, 버튼 이름은 전부
 * '참조' 라 무엇을 누르는지 알 수 없었다. **셋이 똑같아 보이는데 결과는 다르다.**
 *
 * 잘못 누르면 게이지 길이(50mm) 자리에 두께(1mm)가 들어간다. 오류는 안 난다 —
 * 변형률이 50배 커진 그럴듯한 곡선이 나올 뿐이다. 이 프로젝트가 가장 비싸게 겪는
 * "조용히 틀린 성공" 계열이다.
 *
 * 그래서 이름 셋을 화면에 박았는데, 이번엔 반대 문제가 났다 — 규격에 칸을 더해도
 * (자유 길이·직경) 화면이 모른다. 값은 서버가 이미 보내고 있는데 집을 자리가
 * 없어서 사람은 자를 대고 다시 잰다. 이제 **이름이 맞는 것 하나**를 찾는다.
 */

import { describe, expect, it } from 'vitest'

import { isReference, isUsed, referenceFor, referenceLabel } from '@/modules/processing/api'
import type { ProcessingScalar } from '@/modules/processing/api'

const scalar = (key: string, label: string, si_unit = 'm'): ProcessingScalar =>
  ({ key, label, value: 0.05, si_unit, dimension: null }) as unknown as ProcessingScalar

/** 서버가 이 시험에 넣어 주는 값들. 규격이 칸을 정하므로 시험마다 다르다. */
const GIVEN = new Map<string, ProcessingScalar>([
  ['specimen_gauge_length', scalar('specimen_gauge_length', '시편 게이지 길이')],
  ['specimen_width', scalar('specimen_width', '시편 폭')],
  ['specimen_thickness', scalar('specimen_thickness', '시편 두께')],
  ['specimen_free_length', scalar('specimen_free_length', '시편 자유 길이')],
  ['specimen_area', scalar('specimen_area', '시편 초기 단면적', 'm2')],
])

/** 칸 하나. **이름만 있으면 된다** — 나머지는 이 파일이 안 본다. */
const param = (name: string, links_to?: string) => ({ name, links_to })

describe('참조', () => {
  it('게이지 길이에는 게이지 길이만 붙는다', () => {
    // 폭·두께는 단위가 같지만 뜻이 다르다. 이름으로 고르면 구조적으로 하나다.
    expect(referenceFor(param('gauge_length'), GIVEN)?.key).toBe('specimen_gauge_length')
  })

  it('단면적은 면적을 가리킨다', () => {
    expect(referenceFor(param('area'), GIVEN)?.key).toBe('specimen_area')
  })

  it('규격에 칸을 더하면 화면이 저절로 따라온다', () => {
    // **이 파일의 이유.** 전에는 이름 셋이 코드에 박혀 있어서, 값이 와 있어도
    // 집을 자리가 없었다.
    expect(referenceFor(param('free_length'), GIVEN)?.key).toBe('specimen_free_length')
  })

  it('앞 단계가 낸 값도 이름으로 찾는다', () => {
    const carried = new Map([['youngs_modulus', scalar('youngs_modulus', '탄성계수', 'Pa')]])
    expect(referenceFor(param('youngs_modulus'), carried)?.key).toBe('youngs_modulus')
  })

  it('이름이 다르면 칸이 가리키는 것을 따른다', () => {
    // **네킹을 자르는 칸이 그렇다.** `manual_index` 는 앞 단계가 낸
    // `necking_candidate_index` 를 받는데 이름이 다르다 — 이 길이 없으면
    // 사람이 후보 index 를 눈으로 보고 손으로 옮겨 적어야 하고, 곡선을 다시
    // 처리하면 **옛 index 가 남는다.**
    const carried = new Map([
      ['necking_candidate_index', scalar('necking_candidate_index', '네킹 후보 위치')],
    ])
    expect(referenceFor(param('manual_index'), carried)).toBeNull()
    expect(
      referenceFor(param('manual_index', 'necking_candidate_index'), carried)?.key
    ).toBe('necking_candidate_index')
  })

  it('올 값이 없으면 안 붙인다', () => {
    // 없는 값을 가리키면 돌릴 때 "그 값이 없습니다" 로 실패한다. 누르기 전에 막는다.
    expect(referenceFor(param('diameter'), GIVEN)).toBeNull()
  })

  it('원문 대신 사람이 읽는 이름을 보여 준다', () => {
    // `@specimen_gauge_length` 를 그대로 띄우면 이게 무엇인지 코드를 읽어야 안다.
    expect(referenceLabel('@specimen_gauge_length', GIVEN)).toBe('시편 게이지 길이')
  })

  it('모르는 참조는 원문을 그대로 보여 준다', () => {
    // 감추면 "빈 칸" 으로 읽힌다. 모르는 것은 모르는 대로 보여 주는 편이 낫다.
    expect(referenceLabel('@made_up', GIVEN)).toBe('made_up')
    expect(referenceLabel('@made_up')).toBe('made_up')
  })

  it('숫자는 참조가 아니다', () => {
    expect(isReference(0.05)).toBe(false)
    expect(isReference('0.05')).toBe(false)
    expect(isReference('@specimen_area')).toBe(true)
  })
})

describe('안 쓰는 칸', () => {
  const MANUAL_ONLY = { when: { method: ['manual'] } }
  const RANGE_ONLY = { when: { method: ['linear_regression', 'chord', 'secant'] } }

  it('방법을 구간으로 두면 직접 입력이 잠긴다', () => {
    // 잠기지 않으면 거기 넣은 숫자가 **무시된다는 것을 알 방법이 없다.**
    // 값을 넣었는데 아무 일도 안 일어나는 것이 가장 나쁘다.
    expect(isUsed(MANUAL_ONLY, { method: 'linear_regression' })).toBe(false)
    expect(isUsed(RANGE_ONLY, { method: 'linear_regression' })).toBe(true)
  })

  it('방법을 직접 입력으로 두면 구간이 잠긴다', () => {
    expect(isUsed(MANUAL_ONLY, { method: 'manual' })).toBe(true)
    expect(isUsed(RANGE_ONLY, { method: 'manual' })).toBe(false)
  })

  it('조건이 없는 칸은 늘 쓰인다', () => {
    expect(isUsed({}, {})).toBe(true)
    expect(isUsed({ when: null }, { method: 'manual' })).toBe(true)
  })
})
