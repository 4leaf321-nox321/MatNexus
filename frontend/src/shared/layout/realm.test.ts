/**
 * 지금 어느 영역에 서 있는가 — **주소가 정하고, 공용 화면에서는 기억을 따른다.**
 *
 * 알림을 보러 갔다가 사이드바가 다른 세계로 바뀌어 있으면 사람이 「내가 어디
 * 있었더라」 를 묻는다. 반대로 `/composite` 에 링크로 바로 들어왔는데 재료 물성
 * 메뉴가 떠 있으면 그 화면으로 가는 길이 사이드바에 없다.
 */

import { describe, expect, it } from 'vitest'

import { realmOf } from '@/shared/layout/realm'

describe('realmOf', () => {
  it('/composite 아래는 기억과 무관하게 복합 물성이다', () => {
    expect(realmOf('/composite', 'material')).toBe('composite')
    expect(realmOf('/composite/stacks', null)).toBe('composite')
  })

  it('재료 쪽 주소는 기억과 무관하게 재료 물성이다', () => {
    for (const path of ['/materials', '/materials/abc', '/specimens', '/tests', '/test-runs/1', '/cards', '/compare', '/w/metal', '/w/metal/tests/upload']) {
      expect(realmOf(path, 'composite'), path).toBe('material')
    }
  })

  it('공용 화면에서는 마지막 영역을 유지한다', () => {
    for (const path of ['/notifications', '/vocabulary', '/settings/formats', '/w/metal/workbench', '/me']) {
      expect(realmOf(path, 'composite'), path).toBe('composite')
      expect(realmOf(path, 'material'), path).toBe('material')
    }
  })

  it('기억이 없으면 재료 물성이다 — 지금까지의 사이드바 그대로', () => {
    expect(realmOf('/notifications', null)).toBe('material')
  })

  it('/compositeX 같은 비슷한 주소에 속지 않는다', () => {
    expect(realmOf('/composites', null)).toBe('material')
  })
})
