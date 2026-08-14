/**
 * 상단 바 — 사이드바 토글 · 부서 선택 · 테마 · 계정 메뉴.
 *
 * 부서 선택기는 **내가 속한 부서만** 보여 준다. 시스템 관리자라도 여기서는 자기
 * 소속만 오간다 — 전사 목록은 부서 관리 화면의 일이다. 두 목적을 한 위젯에
 * 섞으면 "내 부서"라는 개념이 흐려진다.
 */

import { Building2, Check, ChevronDown, LogOut, Moon, PanelLeft, Sun, User } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { useAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { Separator } from '@/shared/components/ui/separator'
import { NotificationBell } from '@/shared/layout/NotificationBell'
import { useTheme } from '@/shared/theme/ThemeProvider'

interface HeaderProps {
  onToggleSidebar: () => void
  workspaceSlug: string
}

export function Header({ onToggleSidebar, workspaceSlug }: HeaderProps) {
  const { theme, toggle } = useTheme()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const params = useParams<{ slug?: string }>()

  const memberships = user?.memberships ?? []
  const current = memberships.find((m) => m.slug === workspaceSlug)

  async function signOut() {
    await logout()
    navigate('/login', { replace: true })
  }

  function switchTo(slug: string) {
    // 부서 스코프 화면(/w/:slug/...)에 있으면 같은 화면의 다른 부서로, 아니면 홈으로.
    const suffix = params.slug ? window.location.pathname.split(`/w/${params.slug}`)[1] : ''
    navigate(`/w/${slug}${suffix ?? ''}`)
  }

  return (
    <header
      data-app-chrome="header"
      className="bg-background flex h-14 shrink-0 items-center gap-2 border-b px-3"
    >
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggleSidebar}
        aria-label="사이드바 접기/펼치기"
      >
        <PanelLeft className="size-4" />
      </Button>

      <Separator orientation="vertical" className="mx-1 h-6" />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-1.5">
            <Building2 className="size-4" />
            {current?.name ?? workspaceSlug}
            {memberships.length > 1 && <ChevronDown className="size-3 opacity-60" />}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
            내 부서
          </DropdownMenuLabel>
          {memberships.map((membership) => (
            <DropdownMenuItem
              key={membership.slug}
              onClick={() => switchTo(membership.slug)}
              className="justify-between"
            >
              <span className="truncate">{membership.name}</span>
              {membership.slug === workspaceSlug && <Check className="size-4" />}
            </DropdownMenuItem>
          ))}
          {memberships.length === 0 && (
            <DropdownMenuItem disabled>소속된 부서가 없습니다</DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {current?.role === 'manager' && (
        <span className="text-muted-foreground text-xs">부서 관리자</span>
      )}

      <div className="flex-1" />

      <NotificationBell />

      <Button variant="ghost" size="icon" onClick={toggle} aria-label="테마 전환">
        {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            <User className="size-4" />
            {user?.display_name ?? '계정'}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="font-normal">
            <p className="text-sm font-medium">{user?.display_name}</p>
            <p className="text-muted-foreground truncate text-xs">{user?.email}</p>
            {user?.is_system_admin && (
              <p className="text-muted-foreground mt-1 text-xs">시스템 관리자</p>
            )}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={signOut}>
            <LogOut className="size-4" />
            로그아웃
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
