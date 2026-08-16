/**
 * 사이드바가 보여 주는 것 — **눌러야 403 을 아는 메뉴는 메뉴가 아니다.**
 *
 * 사이드바가 역할을 전혀 안 봤다. 평범한 멤버에게도 계정·부서·저장소 정리가
 * 보였고, 누르면 403 이었다. "할 수 있는 일" 을 알려 주지 못하는 화면이다.
 *
 * 반대 방향의 실수가 더 나쁘다 — **볼 수 있는 것을 감추면** 사람은 그 기능이
 * 없는 줄 안다. 그래서 양쪽을 다 시험한다.
 *
 * 이것은 표시일 뿐 권한이 아니다. 권한은 서버가 판정한다(`pytest`).
 */

import { describe, expect, it } from 'vitest'

import { visibleGroups } from '@/shared/layout/navigation'

const MEMBER = { isSystemAdmin: false, isAnyManager: false }
const MANAGER = { isSystemAdmin: false, isAnyManager: true }
const ADMIN = { isSystemAdmin: true, isAnyManager: false }

function labels(viewer: typeof MEMBER): string[] {
  return visibleGroups(viewer).flatMap((group) => group.items.map((item) => item.label))
}

describe('사이드바 메뉴', () => {
  it('평범한 멤버에게 관리 메뉴를 보이지 않는다', () => {
    const seen = labels(MEMBER)
    for (const hidden of ['계정', '부서', '시험 종류', '저장소 정리', '서버', '파일 형식']) {
      expect(seen, hidden).not.toContain(hidden)
    }
  })

  it('멤버도 자기 일은 다 보인다', () => {
    // 감추는 쪽으로 기울면 사람은 기능이 없는 줄 안다.
    const seen = labels(MEMBER)
    for (const shown of ['홈', '시험 데이터', '재료', '공지', '알림']) {
      expect(seen, shown).toContain(shown)
    }
  })

  it('부서 관리자는 장비를 붙이는 데 필요한 것을 다 본다', () => {
    // **장비를 붙이는 것은 사업부의 일이다.** 관리자 전용으로 두었더니 실무가
    // 막혔고, 그래서 프로파일을 부서 소유로 바꿨다(ADR 0004 의 재료와 같은 모델).
    //
    // **시험 종류가 여기 없으면 반쪽이다.** 프로파일은 시험 종류를 가리키는데,
    // 새 장비란 대개 없는 종류를 재는 장비다. 종류를 못 만들면 매핑을 다 끝낸
    // 뒤 저장 순간 403 이 난다(ADR 0006).
    const seen = labels(MANAGER)
    expect(seen).toContain('시험 종류')
    expect(seen).toContain('파일 형식')
    expect(seen).toContain('부서 멤버')
  })

  it('부서 관리자에게 전사 관리 메뉴는 안 보인다', () => {
    const seen = labels(MANAGER)
    expect(seen).not.toContain('계정')
    expect(seen).not.toContain('부서')
    expect(seen).not.toContain('서버')
  })

  it('시스템 관리자는 전부 본다', () => {
    const seen = labels(ADMIN)
    for (const shown of ['계정', '부서', '시험 종류', '파일 형식', '저장소 정리', '서버']) {
      expect(seen, shown).toContain(shown)
    }
  })

  it('빈 그룹은 제목까지 지운다', () => {
    // 항목이 하나도 없는데 제목만 남으면 "뭔가 있는데 안 보인다" 로 읽힌다.
    const titles = visibleGroups(MEMBER).map((group) => group.title)
    expect(titles).not.toContain('관리')
    expect(titles).not.toContain('부서 설정')
    expect(titles).toContain('부서')
  })
})
