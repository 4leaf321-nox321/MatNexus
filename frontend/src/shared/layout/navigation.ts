/**
 * 사이드바 메뉴 정의 (개발계획 §5).
 *
 * 메뉴를 컴포넌트에서 분리해 두는 이유: 어떤 화면이 있어야 하는지가 한 곳에
 * 적혀 있어야 라우터·사이드바·권한이 서로 어긋나지 않는다. RA도 같은 형태다.
 *
 * `resolve` 는 부서(workspace) 스코프 경로다. 부서 모델은 Phase 1에서 들어오고,
 * 그전까지는 DEFAULT_WORKSPACE 를 쓴다.
 */

import {
  Bell,
  BookOpen,
  Boxes,
  Building2,
  FileCode2,
  FileDown,
  FlaskConical,
  GitCompare,
  HardDrive,
  Home,
  ListTree,
  Megaphone,
  MessageSquare,
  Plug,
  Ruler,
  ScrollText,
  Server,
  SlidersHorizontal,
  Tags,
  Trash2,
  User,
  UserCog,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** 부서 모델이 없는 동안 쓰는 임시 slug. Phase 1에서 실제 소속 부서로 대체된다. */
export const DEFAULT_WORKSPACE = 'default'

/**
 * 누구에게 보이는가.
 *
 * **없으면 누르고 나서 403 을 본다.** 지금까지 사이드바가 역할을 안 봐서, 평범한
 * 멤버에게도 계정·부서·저장소 정리가 보였다. 눌러야 권한이 없다는 것을 아는
 * 화면은 "할 수 있는 일" 을 알려 주지 못한다.
 *
 * 이것은 **표시**일 뿐 권한이 아니다. 권한은 서버가 판정한다 — 사이드바를 고쳐
 * 우회할 수 있으면 그건 애초에 보안이 아니다.
 */
export type NavAudience = 'everyone' | 'manager' | 'system_admin'

export interface NavItem {
  label: string
  icon: LucideIcon
  /** 고정 경로 */
  to?: string
  /** 부서 스코프 경로 */
  resolve?: (slug: string) => string
  /** NavLink 의 end 옵션 (부모 경로가 자식에도 활성화되지 않게) */
  end?: boolean
  /** 기본은 `everyone`. */
  audience?: NavAudience
  /** 아직 화면이 없다(stub). 사이드바가 「미구현」 표를 단다 — **자리는 보이되
   *  눌러 보고 알게 하지 않는다.** 화면이 생기면 이 표시를 지운다. */
  pending?: boolean
}

export interface NavGroup {
  title: string
  items: NavItem[]
  /** 그룹 전체가 안 보이는 조건. 항목이 하나도 안 보이면 제목도 지운다. */
  audience?: NavAudience
}

export const NAV_GROUPS: NavGroup[] = [
  {
    // **작업하는 곳.** 여러 시험을 한 줄기로 미는 자리다.
    title: '부서',
    items: [
      { label: '홈', icon: Home, resolve: (s) => `/w/${s}`, end: true },
      { label: '시험 데이터', icon: FlaskConical, resolve: (s) => `/w/${s}/tests` },
      // 워크벤치 5탭이 `시험 선택 → 레시피 적용 → 앙상블 → 피팅 → 솔버 카드` 다.
      //
      // **'통계'와 '내보내기'를 여기서 뺐다.** 계획서 §5 에는 셋이 나란히 있었는데,
      // 그 둘은 워크벤치의 3번·5번 탭과 같은 것이다. 빈 stub 으로 남겨 두었더니
      // 재료 상세의 '물성'·'CAE 카드' 와 이름이 겹쳐, 어느 쪽이 진짜인지 알 수
      // 없었다 — 실제로 "구조가 꼬인 것 같다" 는 말이 나왔다.
      //
      // 자리를 나누는 기준은 **작업이냐 열람이냐** 다. 여러 시험을 골라 미는
      // 것은 워크벤치, "이 재료의 물성이 얼마인가" 는 재료 상세다.
      {
        label: '워크벤치',
        icon: SlidersHorizontal,
        resolve: (s) => `/w/${s}/workbench`,
        pending: true,
      },
    ],
  },
  {
    // **결과를 보는 곳.** 재료 상세가 개요·물성·CAE 카드를 탭으로 갖는다.
    title: '카탈로그',
    items: [
      { label: '재료', icon: Boxes, to: '/materials' },
      // **규격으로 찾는 자리다.** 규격·방향·치수는 시편에 붙는데(ADR 0010)
      // 시편은 재료를 거쳐야만 닿을 수 있었다 — 그래서 규격으로는 아무것도
      // 못 찾았다. 카드가 `/cards` 를 얻은 것과 같은 이유다.
      { label: '시편', icon: ListTree, to: '/specimens' },
      // **재료를 거치지 않고 카드를 찾는다.** 재료 상세의 'CAE 카드' 탭은 그
      // 재료의 것만 보므로, "그 카드가 어느 재료였더라" 에 답할 데가 없었다.
      { label: '물성 카드', icon: FileDown, to: '/cards' },
      { label: '물성 분석', icon: GitCompare, to: '/compare' },
    ],
  },
  {
    title: '내 활동',
    items: [
      { label: '내 작업함', icon: User, to: '/personal', pending: true },
      { label: '알림', icon: Bell, to: '/notifications' },
      // 팝업이었다가 화면이 됐다 — 액세스 토큰까지 붙자 팝업이 좁았다.
      { label: '내 정보', icon: UserCog, to: '/me' },
    ],
  },
  {
    title: '공통',
    items: [
      { label: '공지', icon: Megaphone, to: '/notices' },
      { label: 'VOC', icon: MessageSquare, to: '/voc' },
      { label: '가이드', icon: BookOpen, to: '/guide' },
    ],
  },
  {
    // **부서 관리자가 하는 일.** 형식 프로파일이 부서 소유가 되면서 이 그룹이
    // 필요해졌다 — 장비를 붙이는 것은 사업부의 일이지 시스템 관리자의 일이
    // 아니다. '관리' 에 두면 부서 사람은 자기 일이 아니라고 읽는다.
    title: '부서 설정',
    audience: 'manager',
    items: [
      {
        // **시험 종류도 여기다.** '관리' 에 두었더니 부서 관리자가 새 장비를
        // 붙일 때 막혔다 — 프로파일은 만들 수 있는데 그 프로파일이 가리킬
        // 종류를 못 만들었다. 새 장비란 대개 없는 종류를 재는 장비다(ADR 0006).
        //
        // 채널 키가 전사 자산인 것은 그대로다. 그것은 메뉴가 아니라 **서버의
        // 검사**가 지킨다 — 같은 이름은 같은 차원·단위여야 한다.
        label: '시험 종류',
        icon: ListTree,
        to: '/settings/test-types',
        audience: 'manager',
      },
      { label: '파일 형식', icon: FileCode2, to: '/settings/formats', audience: 'manager' },
      {
        // **장비 PC 가 보낸 파일이 어디까지 왔는지.** 시편을 못 정한 파일을 붙이는
        // 것은 부서 관리자의 일이다 — 재료·프로파일을 만드는 역할과 같다.
        label: '장비 커넥터',
        icon: Plug,
        to: '/settings/connectors',
        audience: 'manager',
      },
      {
        // **만들 수만 있고 볼 수 없으면 자산이 아니다.** 레시피는 처리 탭에서
        // 만들고 목록에서 거는데, 무엇이 저장돼 있는지 보는 자리가 없었다.
        label: '처리 레시피',
        icon: FlaskConical,
        to: '/settings/recipes',
        audience: 'manager',
      },
      {
        // **기록만 쌓이고 볼 자리가 없으면 자산이 아니다.** 레시피·프로파일에서
        // 같은 판단을 했다. 여기에는 만들기·고치기·지우기가 없다 — 고칠 수
        // 있으면 감사가 아니다.
        label: '변경 이력',
        icon: ScrollText,
        to: '/settings/audit',
        audience: 'manager',
      },
      { label: '부서 멤버', icon: Users, resolve: (s) => `/w/${s}/members`, audience: 'manager' },
    ],
  },
  {
    title: '관리',
    audience: 'system_admin',
    items: [
      { label: '계정', icon: UserCog, to: '/admin/accounts', audience: 'system_admin' },
      { label: '부서', icon: Building2, to: '/admin/workspaces', audience: 'system_admin' },
      {
        // **읽기 전용이다.** 환산 계수는 이미 저장된 숫자의 뜻이라 화면에서
        // 못 고친다. 그래도 목록에 두는 이유는, 무엇을 받아 무엇으로 저장하는지가
        // 코드 안에만 있으면 "kgf 를 받나" 를 답할 방법이 없기 때문이다.
        label: '단위',
        icon: Ruler,
        to: '/admin/units',
        audience: 'system_admin',
      },
      {
        // **기준정보를 켜 두고 고칠 데가 없으면 절반만 한 것이다.** 오타가 값이
        // 되면 그것을 고르는 다음 사람이 생기고, 오염이 자기 강화된다.
        label: '기준정보',
        icon: Tags,
        to: '/admin/vocabulary',
        audience: 'system_admin',
      },
      { label: '저장소 정리', icon: HardDrive, to: '/admin/storage', audience: 'system_admin' },
      {
        // **지운 것이 어디로 갔는지 볼 자리.** 삭제가 소프트라 행은 남는데
        // 볼 데가 없어서, 지운 재료가 이름을 붙들고 있는 것을 아무도 설명할
        // 수 없었다(2026-08-28 이관 사고).
        label: '휴지통',
        icon: Trash2,
        to: '/admin/trash',
        audience: 'system_admin',
      },
      { label: '서버', icon: Server, to: '/server', audience: 'system_admin', pending: true },
    ],
  },
]

export function itemHref(item: NavItem, slug: string): string {
  return item.to ?? item.resolve?.(slug) ?? '/'
}

/** 이 사람에게 보이는가. 서버가 최종 판정을 한다 — 여기는 표시일 뿐이다. */
export function canSee(
  audience: NavAudience | undefined,
  viewer: { isSystemAdmin: boolean; isAnyManager: boolean }
): boolean {
  if (audience === 'system_admin') return viewer.isSystemAdmin
  if (audience === 'manager') return viewer.isSystemAdmin || viewer.isAnyManager
  return true
}

/** 볼 수 있는 것만 남긴 메뉴. 빈 그룹은 제목까지 지운다. */
export function visibleGroups(viewer: {
  isSystemAdmin: boolean
  isAnyManager: boolean
}): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => canSee(item.audience, viewer)),
  })).filter((group) => canSee(group.audience, viewer) && group.items.length > 0)
}
