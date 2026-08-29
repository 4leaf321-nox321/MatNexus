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

import { readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { NAV_GROUPS, visibleGroups } from '@/shared/layout/navigation'

const MEMBER = { isSystemAdmin: false, isAnyManager: false }
const MANAGER = { isSystemAdmin: false, isAnyManager: true }
const ADMIN = { isSystemAdmin: true, isAnyManager: false }

function labels(viewer: typeof MEMBER): string[] {
  return visibleGroups(viewer).flatMap((group) => group.items.map((item) => item.label))
}

describe('사이드바 메뉴', () => {
  it('평범한 멤버에게 관리 메뉴를 보이지 않는다', () => {
    const seen = labels(MEMBER)
    for (const hidden of ['계정', '부서 정보', '서버', '부서 멤버', '변경 이력']) {
      expect(seen, hidden).not.toContain(hidden)
    }
  })

  it('멤버도 수집 체계는 본다 — 고치지만 못 할 뿐이다', () => {
    // **막고 있던 것은 사이드바뿐이었다.** 서버의 읽기 엔드포인트는 넷 다 이미
    // `current_user` 였다. 그런데 메뉴가 없어서 실험한 사람이 「내 파일이 왜 안
    // 들어왔나」·「이 장비 형식이 뭘로 잡혀 있나」 를 물을 데가 없었다.
    //
    // 쓰기 단추는 화면이 가린다(`shared/auth/roles`) — 눌러 보고 403 을 알게
    // 하지 않는다.
    const seen = labels(MEMBER)
    for (const shown of ['장비 커넥터', '인풋 파일 정의', '시험 정의', '레시피 목록']) {
      expect(seen, shown).toContain(shown)
    }
  })

  it('멤버도 자기 일은 다 보인다', () => {
    // 감추는 쪽으로 기울면 사람은 기능이 없는 줄 안다.
    const seen = labels(MEMBER)
    for (const shown of ['홈', '시험', '재료', '공지 · VOC', '알림']) {
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
    expect(seen).toContain('시험 정의')
    expect(seen).toContain('인풋 파일 정의')
    expect(seen).toContain('레시피 목록')
    expect(seen).toContain('부서 멤버')
  })

  it('부서 관리자에게 전사 관리 메뉴는 안 보인다', () => {
    const seen = labels(MANAGER)
    expect(seen).not.toContain('계정')
    expect(seen).not.toContain('부서 정보')
    expect(seen).not.toContain('서버')
  })

  it('시스템 관리자는 전부 본다', () => {
    const seen = labels(ADMIN)
    for (const shown of ['계정', '부서 정보', '시험 정의', '인풋 파일 정의', '서버']) {
      expect(seen, shown).toContain(shown)
    }
  })

  it('빈 그룹은 제목까지 지운다', () => {
    // 항목이 하나도 없는데 제목만 남으면 "뭔가 있는데 안 보인다" 로 읽힌다.
    const titles = visibleGroups(MEMBER).map((group) => group.title)
    expect(titles).not.toContain('관리')
    expect(titles).not.toContain('내 부서')
    expect(titles).toContain('카탈로그')
  })
})

describe('자리', () => {
  it('데이터 사슬이 한 그룹에 차례대로 선다', () => {
    // **차례가 뜻이다.** 재료에서 시편을 뜨고 시편으로 시험을 하고 그 결과가
    // 카드가 된다. 시험만 다른 그룹('부서')에 있었고, 그래서 시편에서 시험으로
    // 가는 길이 사이드바에 안 보였다.
    const catalog = NAV_GROUPS.find((group) => group.title === '카탈로그')
    const labels = catalog?.items.map((item) => item.label) ?? []
    expect(labels.slice(0, 4)).toEqual(['재료', '시편', '시험', '물성 카드'])
  })

  it('카탈로그는 전부 전역 경로다 — 하나만 부서로 좁으면 「이것뿐인가」 가 된다', () => {
    // 시험이 `/w/<부서>/tests` 였다. 재료·시편은 다 보이는데 시험만 자기 부서
    // 것만 보이면, 그 목록이 짧은 이유를 화면에서 알 수 없다.
    const catalog = NAV_GROUPS.find((group) => group.title === '카탈로그')
    for (const item of catalog?.items ?? []) {
      expect(item.resolve, item.label).toBeUndefined()
      expect(item.to, item.label).toBeTruthy()
    }
  })

  it('고르는 사람이 기준정보를 본다 — 다만 고치는 자리는 아니다', () => {
    // **막고 있던 것은 화면뿐이었다.** 서버의 읽기 엔드포인트는 이미 `current_user`
    // 다. 값을 매일 드롭다운에서 고르는 것은 멤버인데 목록을 못 보면, 찾는 값이
    // 없을 때 「아직 없다」 인지 「이름이 다르다」 인지 구별할 수 없다.
    const seen = labels(MEMBER)
    expect(seen).toContain('기준정보')
    // 고치는 화면은 여전히 관리자만이다 — 이름이 달라야 어느 쪽인지 안다.
    expect(seen).not.toContain('기준정보 편집')
    expect(labels(ADMIN)).toContain('기준정보 편집')
  })

  it('단위는 메뉴에 따로 안 선다 — 기준정보 안의 한 칸이다', () => {
    // 둘로 세우면 「단위가 기준정보가 아닌가」 를 묻게 된다. 화면 왼쪽 축 목록
    // 에서 선 아래 따로 세운다(VocabularyPage).
    expect(labels(ADMIN)).not.toContain('단위')
  })

  it('공지와 VOC 는 한 항목이다', () => {
    // 둘로 서 있으면 「어느 쪽에 쓰지」 를 매번 묻는다. 주소는 둘로 남아 있고
    // 화면 안에서 탭으로 갈린다 — 공지 하나를 링크로 가리킬 수 있어야 한다.
    const seen = labels(MEMBER)
    expect(seen).toContain('공지 · VOC')
    expect(seen).not.toContain('VOC')
  })

  it('수집 체계는 사슬 차례로 선다', () => {
    // **정의 셋을 갖춰 놓고 마지막에 장비를 붙인다.** 앞 셋은 「무엇을 어떻게
    // 받고 처리할지」 를 미리 적는 자리고, 커넥터는 그 정의를 따라 실제로 들어온
    // 파일을 다루는 자리다 — 새로 붙이는 사람의 일 순서가 그대로 차례다.
    const chain = NAV_GROUPS.find((group) => group.title === '데이터 수집 체계')
    expect(chain?.items.map((item) => item.label)).toEqual([
      '시험 정의',
      '인풋 파일 정의',
      '레시피 목록',
      '장비 커넥터',
    ])
  })

  it('사슬이 아닌 것은 그 그룹에 안 넣는다', () => {
    // 「부서 설정」 이 애매했던 까닭이다 — 권한(누가 하나)으로 이름을 붙이자
    // 성격이 다른 여섯이 한 이름 아래 모였고, 그 이름이 아무것도 안 말했다.
    const chain = NAV_GROUPS.find((group) => group.title === '데이터 수집 체계')
    const labels = chain?.items.map((item) => item.label) ?? []
    expect(labels).not.toContain('부서 멤버')
    expect(labels).not.toContain('변경 이력')

    const workspace = NAV_GROUPS.find((group) => group.title === '내 부서')
    expect(workspace?.items.map((item) => item.label)).toEqual(['부서 멤버', '변경 이력'])
  })

  it('그룹 이름이 항목 이름과 겹치지 않는다', () => {
    // 시스템 관리자에게는 '관리 > 부서'(전사 목록)가 함께 보인다. 그룹까지
    // '부서' 면 어느 쪽이 무엇인지 알 수 없다 — 기준정보에서 겪은 것과 같다.
    const titles = NAV_GROUPS.map((group) => group.title).filter(Boolean)
    const items = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.label))
    for (const title of titles) {
      expect(items, title).not.toContain(title)
    }
  })

  it('워크벤치는 내 활동에 있다 — 개인이 벌여 놓는 작업대다', () => {
    const mine = NAV_GROUPS.find((group) => group.title === '내 활동')
    expect(mine?.items.map((item) => item.label)).toContain('워크벤치')
  })

  it('홈은 제목 없이 맨 위에 혼자 선다', () => {
    // 「부서」 라는 제목 아래 홈 하나만 남았었다. 제목은 「여기 여럿이 있다」 는
    // 신호라서, 하나뿐인데 달면 못 찾은 항목이 있는 줄 안다.
    const [first] = NAV_GROUPS
    expect(first.title).toBeUndefined()
    expect(first.items.map((item) => item.label)).toEqual(['홈'])
  })
})

describe('미구현 표시', () => {
  it('stub 화면만 pending 이다 — 화면이 생기면 지운다', () => {
    const pending = NAV_GROUPS.flatMap((group) => group.items)
      .filter((item) => item.pending)
      .map((item) => item.label)
    // router.tsx 의 stub() 목록과 짝이다. 화면을 만들었으면 여기서 빼야 한다.
    expect(pending.sort()).toEqual(['내 작업함', '워크벤치'])
  })

  it('서버는 이제 화면이 있다 — 저장소 정리를 그 아래 탭으로 품는다', () => {
    // 둘은 같은 질문의 두 쪽이다: 「우리가 쌓은 것」 과 「드라이브에 남은 것」.
    // 따로 서 있으면 디스크가 찰 때 한쪽만 보고 「치울 게 없다」 고 끝낸다.
    const seen = labels(ADMIN)
    expect(seen).toContain('서버')
    expect(seen).not.toContain('저장소 정리')
  })
})

describe('e2e 가 누르는 이름', () => {
  /**
   * **이름을 바꿀 때마다 여기서 먼저 걸려야 한다.**
   *
   * 스모크는 사이드바를 눌러서 화면에 닿는다 — 주소로 바로 열면 「메뉴가 옮겨가서
   * 못 찾는」 사고를 못 잡기 때문이고, 그 판단은 옳다. 대신 **이름을 바꾸면 그
   * 시험이 깨진다.** 실제로 두 번 그랬다:
   *
   *     v1.161.0  홈 카드 문구를 바꾸고 e2e 만 안 고쳤다
   *     v1.164.0  '파일 형식' → '인풋 파일 정의' 로 바꾸고 e2e 만 안 고쳤다
   *
   * 둘 다 **CI 에서 14분 걸려 알았다.** e2e 는 서버 둘과 브라우저가 필요해 손에서
   * 안 돌리니, 여기서 55초에 잡는다.
   *
   * 화면을 열지 않는다 — 스모크 파일에서 **사이드바를 집는 줄**만 읽어 그 이름이
   * `NAV_GROUPS` 에 있는지 본다.
   */
  it('스모크가 누르는 사이드바 항목이 실제로 있다', () => {
    const spec = readFileSync(
      path.resolve(process.cwd(), 'e2e/smoke.spec.ts'),
      'utf-8'
    )
    // `[data-app-chrome="sidebar"]` 로 좁힌 뒤 이름으로 집는 자리만 본다.
    const wanted = [...spec.matchAll(/data-app-chrome="sidebar"[\s\S]{0,200}?name: '([^']+)'/g)].map(
      (found) => found[1]
    )
    expect(wanted.length, '스모크가 사이드바를 안 누른다면 이 시험이 지킬 것도 없다').toBeGreaterThan(0)

    const labels = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.label))
    for (const name of wanted) {
      expect(labels, `스모크가 '${name}' 를 누르는데 사이드바에 그런 항목이 없다`).toContain(name)
    }
  })
})

