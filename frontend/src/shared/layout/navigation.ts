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

export interface NavItem {
  label: string
  icon: LucideIcon
  /** 고정 경로 */
  to?: string
  /** 부서 스코프 경로 */
  resolve?: (slug: string) => string
  /** NavLink 의 end 옵션 (부모 경로가 자식에도 활성화되지 않게) */
  end?: boolean
}

export interface NavGroup {
  title: string
  items: NavItem[]
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
    title: '관리',
    items: [
      { label: '계정', icon: UserCog, to: '/admin/accounts' },
      { label: '부서', icon: Building2, to: '/admin/workspaces' },
      { label: '부서 멤버', icon: Users, resolve: (s) => `/w/${s}/members` },
      { label: '시험종류 정의', icon: ListTree, to: '/admin/test-types' },
      { label: '형식 프로파일', icon: FileCode2, to: '/admin/formats' },
      { label: '장비 커넥터', icon: Plug, to: '/admin/connectors' },
      { label: '저장소 정리', icon: HardDrive, to: '/admin/storage' },
      { label: '서버', icon: Server, to: '/server' },
    ],
  },
]

export function itemHref(item: NavItem, slug: string): string {
  return item.to ?? item.resolve?.(slug) ?? '/'
}
