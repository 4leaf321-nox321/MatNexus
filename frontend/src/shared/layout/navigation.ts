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
  BarChart3,
  Bell,
  BookOpen,
  Boxes,
  Building2,
  Download,
  FileCode2,
  FlaskConical,
  GitCompare,
  HardDrive,
  Home,
  ListTree,
  Megaphone,
  MessageSquare,
  Plug,
  Server,
  SlidersHorizontal,
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
}

export interface NavGroup {
  title: string
  items: NavItem[]
  /** 그룹 전체가 안 보이는 조건. 항목이 하나도 안 보이면 제목도 지운다. */
  audience?: NavAudience
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: '부서',
    items: [
      { label: '홈', icon: Home, resolve: (s) => `/w/${s}`, end: true },
      { label: '시험 데이터', icon: FlaskConical, resolve: (s) => `/w/${s}/tests` },
      { label: '워크벤치', icon: SlidersHorizontal, resolve: (s) => `/w/${s}/workbench` },
      { label: '통계', icon: BarChart3, resolve: (s) => `/w/${s}/statistics` },
      { label: '내보내기', icon: Download, resolve: (s) => `/w/${s}/exports` },
    ],
  },
  {
    title: '카탈로그',
    items: [
      { label: '재료', icon: Boxes, to: '/materials' },
      { label: '곡선 비교', icon: GitCompare, to: '/compare' },
    ],
  },
  {
    title: '내 활동',
    items: [
      { label: '내 작업함', icon: User, to: '/personal' },
      { label: '알림', icon: Bell, to: '/notifications' },
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
      { label: '부서 멤버', icon: Users, resolve: (s) => `/w/${s}/members`, audience: 'manager' },
    ],
  },
  {
    title: '관리',
    audience: 'system_admin',
    items: [
      { label: '계정', icon: UserCog, to: '/admin/accounts', audience: 'system_admin' },
      { label: '부서', icon: Building2, to: '/admin/workspaces', audience: 'system_admin' },
      { label: '장비 커넥터', icon: Plug, to: '/admin/connectors', audience: 'system_admin' },
      { label: '저장소 정리', icon: HardDrive, to: '/admin/storage', audience: 'system_admin' },
      { label: '서버', icon: Server, to: '/server', audience: 'system_admin' },
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
