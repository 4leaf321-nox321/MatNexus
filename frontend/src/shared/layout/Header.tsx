/**
 * 상단 바 — 사이드바 토글 · 부서 선택 · 테마 · 계정 메뉴.
 *
 * 부서 선택기는 **내가 속한 부서만** 보여 준다. 시스템 관리자라도 여기서는 자기
 * 소속만 오간다 — 전사 목록은 부서 관리 화면의 일이다. 두 목적을 한 위젯에
 * 섞으면 "내 부서"라는 개념이 흐려진다.
 */

import { useState } from 'react'
import {
  KeyRound,
  LogOut,
  Moon,
  PanelLeft,
  PanelLeftClose,
  PanelRight,
  Sun,
  User,
  UserCog,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { useLeftPanel, useRightPanel } from '@/shared/layout/SidePanel'
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
import { ChangePasswordDialog } from '@/shared/layout/ChangePasswordDialog'
import { ProfileDialog } from '@/shared/layout/ProfileDialog'
import { NotificationBell } from '@/shared/layout/NotificationBell'
import { useTheme } from '@/shared/theme/ThemeProvider'

interface HeaderProps {
  onToggleSidebar: () => void
  workspaceSlug: string
}

export function Header({ onToggleSidebar, workspaceSlug }: HeaderProps) {
  const { theme, toggle } = useTheme()
  const rightPanel = useRightPanel()
  const leftPanel = useLeftPanel()
  const { user, logout, reload } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)
  const [editingProfile, setEditingProfile] = useState(false)
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

      {/* **왼쪽 영역을 여는 단추.** 사이드바 토글 바로 옆이다 — 껍데기를 여닫는
          단추는 다 여기 있다. 화면이 그 자리를 쓸 때만 뜬다. */}
      {leftPanel.label && (
        <Button
          variant={leftPanel.open ? 'secondary' : 'ghost'}
          size="icon"
          onClick={leftPanel.toggle}
          aria-pressed={leftPanel.open}
          aria-label={`${leftPanel.label} ${leftPanel.open ? '접기' : '펴기'}`}
          title={leftPanel.label}
        >
          <PanelLeftClose className="size-4" />
        </Button>
      )}

      <Separator orientation="vertical" className="mx-1 h-6" />

      {/* **경로가 보이는 선택기.** 소속이 여러 곳이면 `품질팀` 이 둘일 수 있고,
          이름만 보여 주면 지금 어느 부서에 있는지 알 수 없다. 부서가 많아지면
          검색으로 좁힌다 — 목록이 길어질수록 드롭다운은 못 쓰게 된다. */}
      <WorkspacePicker
        workspaces={memberships}
        value={workspaceSlug}
        onChange={switchTo}
        className="h-8 max-w-64 border-0 shadow-none"
        placeholder={workspaceSlug}
        emptyLabel="소속된 부서가 없습니다"
      />

      {current?.role === 'manager' && (
        <span className="text-muted-foreground text-xs">부서 관리자</span>
      )}

      <div className="flex-1" />

      <NotificationBell />

      {/* **오른쪽 영역을 여는 단추.** 화면이 그 자리를 쓸 때만 뜬다 — 없는
          패널을 여는 단추가 남아 있으면 눌러도 아무 일이 안 일어난다.
          처음에는 접힌 사이드바를 화면 오른쪽 끝에 흐린 세로 띠로 뒀는데
          아무도 못 봤다. 껍데기를 여닫는 단추는 왼쪽 토글과 같은 자리에 있어야
          한다. */}
      {rightPanel.label && (
        <Button
          variant={rightPanel.open ? 'secondary' : 'ghost'}
          size="icon"
          onClick={rightPanel.toggle}
          aria-pressed={rightPanel.open}
          aria-label={`${rightPanel.label} ${rightPanel.open ? '접기' : '펴기'}`}
          title={rightPanel.label}
        >
          <PanelRight className="size-4" />
        </Button>
      )}

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
          {/* **스스로 바꿀 자리가 없었다.** 관리자에게 재설정을 부탁해 임시
              비밀번호를 받는 길밖에 없었고, 관리자 자신은 그 길조차 없었다. */}
          <DropdownMenuItem onClick={() => setEditingProfile(true)}>
            <UserCog className="size-4" />
            내 정보
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setChangingPassword(true)}>
            <KeyRound className="size-4" />
            비밀번호 변경
          </DropdownMenuItem>
          <DropdownMenuItem onClick={signOut}>
            <LogOut className="size-4" />
            로그아웃
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 바꾸고 나면 서버가 세션을 전부 끊는다 — 클라이언트 상태도 맞춘다. */}
      <ProfileDialog
        open={editingProfile}
        email={user?.email ?? ''}
        displayName={user?.display_name ?? ''}
        onClose={() => setEditingProfile(false)}
        onSaved={async () => {
          setEditingProfile(false)
          // 상단 바가 바로 새 이름을 보여야 한다 — 저장했는데 안 바뀌면 실패로 읽힌다.
          await reload()
        }}
      />

      <ChangePasswordDialog
        open={changingPassword}
        onClose={() => setChangingPassword(false)}
        onChanged={async () => {
          setChangingPassword(false)
          await logout()
        }}
      />
    </header>
  )
}
